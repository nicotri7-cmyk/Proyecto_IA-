"""
main.py
Servidor FastAPI para el Kiosco de Pedidos por Voz con IA, control de stock y tool calling local.
Soporta pedidos regulares y armado de SANDWICHES PERSONALIZADOS según disponibilidad de ingredientes en SQLite.
"""

import os
import re
import json
import shutil
import uuid
import logging
import sqlite3
from contextlib import asynccontextmanager
from typing import List, Optional, Dict, Any, Tuple

from fastapi import FastAPI, Depends, HTTPException, File, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from openai import OpenAI

from database import Base, engine, SessionLocal, get_db
from models import Producto, Pedido, DetallePedido, seed_data, DIET_INFO_DEFAULT

# Configuración de logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("kiosco-voz")

# Configuración de cliente OpenAI apuntando a Ollama
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434/v1")
MODEL_NAME = os.getenv("MODEL_NAME", "llama3.2:1b")
openai_client = OpenAI(base_url=OLLAMA_BASE_URL, api_key="ollama")

# Directorio de subidas de archivos
STATIC_DIR = os.path.join(os.path.dirname(__file__), "static")
UPLOADS_DIR = os.path.join(STATIC_DIR, "uploads")
os.makedirs(UPLOADS_DIR, exist_ok=True)

# Memoria de conversación en RAM por sesión
session_histories: Dict[str, List[Dict[str, Any]]] = {}
# Estado para el armado secuencial de sandwiches personalizados (Obligatorio: Base primero, Ingredientes después)
session_sandwich_state: Dict[str, Dict[str, Any]] = {}

# Prompt del sistema adaptado para pedidos regulares y sandwiches personalizados con base obligatoria
SYSTEM_PROMPT = (
    "Eres un asistente de compras rápido y cordial de Voice Bistro. Tu trabajo es armar pedidos y sandwiches personalizados según los ingredientes en stock. "
    "REGLA OBLIGATORIA PARA SANDWICHES PERSONALIZADOS: Es obligatorio que el cliente elija primero el pan (base) antes de los ingredientes. "
    "Nunca armes un sandwich sin base. Si el cliente aún no ha elegido pan, pídele amablemente que escoja su pan primero. "
    "Una vez que el cliente tenga su pan seleccionado, invítalo a elegir los ingredientes (proteínas, agregados y salsas). "
    "NUNCA inventes precios ni confirmes un pedido sin antes ejecutar la función 'consultar_inventario'. "
    "Si un producto o ingrediente tiene stock 0, avisa amablemente que no queda y ofrece un sustituto de la misma categoría que sí tenga stock. "
    "Responde siempre en español, de forma muy breve y directa (máximo 2 oraciones cortas)."
)

# Esquema de herramientas minimalista para llama3.2:1b
TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "consultar_inventario",
            "description": "Busca productos o ingredientes en el catálogo por nombre o categoría (Panes, Proteínas, Agregados, Salsas, Comidas, Bebidas).",
            "parameters": {
                "type": "object",
                "properties": {
                    "termino_busqueda": {
                        "type": "string",
                        "description": "Término a buscar (ej: 'hamburguesa', 'pan', 'mechada', 'palta', 'ingredientes').",
                    }
                },
                "required": ["termino_busqueda"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "agregar_al_pedido",
            "description": "Agrega un producto regular al pedido actual del cliente y descuenta su stock.",
            "parameters": {
                "type": "object",
                "properties": {
                    "producto_id": {
                        "type": "integer",
                        "description": "ID numérico exacto del producto a agregar.",
                    },
                    "cantidad": {
                        "type": "integer",
                        "description": "Cantidad de unidades (entero positivo, ej: 1, 2).",
                    },
                },
                "required": ["producto_id", "cantidad"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "armar_sandwich_personalizado",
            "description": "Arma un sandwich personalizado combinando múltiples ingredientes (pan, proteína, agregados, salsas) con control de stock individual.",
            "parameters": {
                "type": "object",
                "properties": {
                    "ingredientes_ids": {
                        "type": "array",
                        "items": {"type": "integer"},
                        "description": "Lista de IDs numéricos de los ingredientes elegidos para el sandwich.",
                    }
                },
                "required": ["ingredientes_ids"],
            },
        },
    },
]


# ==========================================
# LIFESPAN (INICIALIZACIÓN Y WARM-UP)
# ==========================================
@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Inicializa la base de datos, ejecuta seed_data con ingredientes
    y pre-carga el modelo llama3.2:1b en la GPU/VRAM de Ollama.
    """
    logger.info("Iniciando aplicación: inicializando base de datos SQLite...")
    Base.metadata.create_all(bind=engine)

    # Migración de esquema en caliente para columnas imagen_url y activo si no existiesen
    try:
        conn = sqlite3.connect("pedidos.db")
        cur = conn.cursor()
        cur.execute("PRAGMA table_info(productos)")
        columnas = [col[1] for col in cur.fetchall()]
        if "imagen_url" not in columnas:
            logger.info("[MIGRACIÓN] Agregando columna imagen_url a tabla productos...")
            cur.execute("ALTER TABLE productos ADD COLUMN imagen_url VARCHAR(500)")
            conn.commit()
        if "activo" not in columnas:
            logger.info("[MIGRACIÓN] Agregando columna activo a tabla productos...")
            cur.execute("ALTER TABLE productos ADD COLUMN activo INTEGER NOT NULL DEFAULT 1")
            conn.commit()
        if "tipo_personalizado" not in columnas:
            logger.info("[MIGRACIÓN] Agregando columna tipo_personalizado a tabla productos...")
            cur.execute("ALTER TABLE productos ADD COLUMN tipo_personalizado VARCHAR(30) NOT NULL DEFAULT 'ninguno'")
            cur.execute("UPDATE productos SET tipo_personalizado = 'base' WHERE categoria = 'Panes'")
            cur.execute("UPDATE productos SET tipo_personalizado = 'ingrediente' WHERE categoria IN ('Proteínas', 'Agregados', 'Salsas')")
            cur.execute("UPDATE productos SET tipo_personalizado = 'ninguno' WHERE categoria NOT IN ('Panes', 'Proteínas', 'Agregados', 'Salsas')")
            conn.commit()
        if "es_vegetariano" not in columnas:
            logger.info("[MIGRACIÓN] Agregando columna es_vegetariano a tabla productos...")
            cur.execute("ALTER TABLE productos ADD COLUMN es_vegetariano INTEGER NOT NULL DEFAULT 0")
            conn.commit()
        if "es_vegano" not in columnas:
            logger.info("[MIGRACIÓN] Agregando columna es_vegano a tabla productos...")
            cur.execute("ALTER TABLE productos ADD COLUMN es_vegano INTEGER NOT NULL DEFAULT 0")
            conn.commit()
        
        # Backfill dietas predeterminadas
        for prod_nom, (d_veg, d_vegan) in DIET_INFO_DEFAULT.items():
            cur.execute(
                "UPDATE productos SET es_vegetariano = ?, es_vegano = ? WHERE nombre = ?",
                (1 if d_veg else 0, 1 if d_vegan else 0, prod_nom)
            )
        conn.commit()
        conn.close()
    except Exception as em:
        logger.warning(f"Aviso en verificación de esquema SQLite: {em}")

    # Semillero inicial de datos con ingredientes e imágenes
    db = SessionLocal()
    try:
        seed_data(db)
    finally:
        db.close()

    # Pre-carga (Warm-up) de llama3.2:1b en Ollama
    logger.info(f"Enviando ping de warm-up a Ollama ({MODEL_NAME}) en {OLLAMA_BASE_URL}...")
    try:
        openai_client.chat.completions.create(
            model=MODEL_NAME,
            messages=[{"role": "user", "content": "ping"}],
            max_tokens=2,
        )
        logger.info(f"Warm-up completado exitosamente: el modelo '{MODEL_NAME}' está activo en VRAM.")
    except Exception as e:
        logger.warning(f"Advertencia durante warm-up con Ollama: {e}")

    yield

    logger.info("Cerrando aplicación Kiosco de Pedidos...")


app = FastAPI(
    title="Kiosco de Pedidos por Voz con IA",
    description="Prototipo de pedidos por voz con Ollama (llama3.2:1b), control de stock y sandwiches personalizados en SQLite.",
    version="1.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ==========================================
# UTILIDADES DE PARSEO Y ANÁLISIS DE TEXTO
# ==========================================
def extraer_tool_call_desde_texto(texto: str):
    """Extrae llamada a función si el modelo la emitió en bloque de texto JSON en lugar de tool_calls."""
    if not texto:
        return None

    def _extraer_fn_de_dict(d: dict):
        if not isinstance(d, dict):
            return None
        fn_name = d.get("name")
        fn_params = d.get("parameters") or d.get("arguments") or {}
        if not fn_name and isinstance(d.get("function"), dict):
            fn_name = d["function"].get("name")
            fn_params = d["function"].get("parameters") or d["function"].get("arguments") or {}
        if fn_name:
            return fn_name, fn_params
        return None

    m1 = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", texto, re.DOTALL)
    if m1:
        try:
            d = json.loads(m1.group(1))
            res = _extraer_fn_de_dict(d)
            if res:
                return res
        except Exception:
            pass

    m2 = re.search(r"(\{\s*\"(?:type|name|function)\".*?\})", texto, re.DOTALL)
    if m2:
        try:
            d = json.loads(m2.group(1))
            res = _extraer_fn_de_dict(d)
            if res:
                return res
        except Exception:
            pass

    return None


class SyntheticFunction:
    def __init__(self, name: str, arguments: dict):
        self.name = name
        self.arguments = json.dumps(arguments)


class SyntheticToolCall:
    def __init__(self, id_call: str, name: str, arguments: dict):
        self.id = id_call
        self.function = SyntheticFunction(name, arguments)


def extraer_cantidad_desde_texto(texto: str) -> int:
    """Extrae cantidad numérica expresada en palabras o dígitos."""
    palabras_num = {
        "un": 1, "una": 1, "uno": 1,
        "dos": 2, "tres": 3, "cuatro": 4, "cinco": 5, "seis": 6
    }
    texto_l = texto.lower()
    for pal, num in palabras_num.items():
        if re.search(r"\b" + pal + r"\b", texto_l):
            return num
    match = re.search(r"\b(\d+)\b", texto_l)
    if match:
        return max(1, int(match.group(1)))
    return 1


def clasificar_intencion(mensaje: str) -> str:
    """
    Distingue con precisión si el usuario está haciendo una pregunta/consulta ('CONSULTA')
    o si está dando una orden explícita de agregar al pedido ('ORDENAR').
    """
    m = mensaje.lower().strip()

    # 1. Signos o frases que denotan inequívocamente una pregunta o consulta informativa
    patrones_pregunta = [
        "?", "¿", "qué ", "que ", "cuál ", "cual ", "cuáles ", "cuales ",
        "cuánto ", "cuanto ", "cuántos ", "cuantos ", "cómo ", "como ",
        "tienes", "tienen", "hay ", "queda ", "quedan ", "venden ",
        "cuéntame", "cuentame", "explícame", "explicame", "dime ", "dinos ",
        "puedes decirme", "me puedes decir", "me dices", "sabes si",
        "quiero saber", "quisiera saber", "deseo saber", "gustaría saber", "gustaria saber",
        "recomiéndame", "recomiendame", "recomienda", "sugieres", "sugerencia",
        "precio", "precios", "vale ", "valen ", "costo", "costos",
        "opciones", "carta", "menú", "menu", "catálogo", "catalogo",
        "ingredientes", "ingrediente", "hola", "buenas", "buenos días", "buenas tardes", "buenas noches"
    ]

    es_consulta = any(p in m for p in patrones_pregunta)

    # Si contiene indicadores de consulta y no arranca con un verbo imperativo directo de compra:
    verbos_orden_inicio = ["agrega ", "añade ", "pon en mi pedido ", "pídeme ", "arma un ", "armar un ", "hazme un "]
    if es_consulta and not any(m.startswith(v) for v in verbos_orden_inicio):
        return "CONSULTA"

    # 2. Verbos imperativos de compra explícitos
    verbos_ordenar = [
        "agrega", "agregar", "añade", "añadir", "anota", "anotar",
        "pon en mi pedido", "incluye", "pídeme", "arma un sandwich", "armar un sandwich", "hazme un sandwich"
    ]

    for v in verbos_ordenar:
        if v in m and not es_consulta:
            return "ORDENAR"

    if m.startswith(("quiero pedir ", "quiero comprar ", "quiero agregar ", "dame ", "un ", "una ", "dos ", "tres ", "4 ", "5 ")):
        return "ORDENAR"

    if m.startswith("quiero ") and not any(w in m for w in ["saber", "preguntar", "conocer", "ver"]):
        return "ORDENAR"

    return "CONSULTA"


def es_intencion_sandwich_custom(texto: str) -> bool:
    """Detecta si el usuario tiene intención de armar, personalizar o consultar ingredientes para un sandwich."""
    if not texto:
        return False
    t = texto.lower()
    t_clean = (
        t.replace("á", "a")
        .replace("é", "e")
        .replace("í", "i")
        .replace("ó", "o")
        .replace("ú", "u")
    )

    # Expresiones directas de armar/crear/personalizar sandwich y consultas de ingredientes
    keywords_directas = [
        "armar sandwich", "armar un sandwich", "arma un sandwich", "armar el sandwich", "arma el sandwich",
        "armar mi sandwich", "armarme un sandwich", "arma mi sandwich", "armate un sandwich",
        "hacer un sandwich", "hazme un sandwich", "hacer sandwich", "hazme sandwich",
        "crear sandwich", "crear un sandwich",
        "sandwich personalizado", "sánguche personalizado", "sanguche personalizado", "sandwish personalizado",
        "sandiwch personalizado", "sanduche personalizado", "sandwhich personalizado",
        "personalizar sandwich", "personalizar un sandwich", "personalizar", "personalizado", "personalizada",
        "ingredientes para armar", "ingredientes para el sandwich", "ingredientes del sandwich",
        "ingredientes para sandwich", "opciones para armar", "ingrediente", "ingredientes",
        "que ingredientes", "cuales son los ingredientes", "opciones de pan", "opciones de panes",
        "que panes", "bases disponibles"
    ]
    if any(k in t_clean for k in keywords_directas):
        return True

    # Si contiene cualquier variante de la palabra sandwich/sánguche
    variantes_sandwich = ["sandwich", "sandiwch", "sandwish", "sandwhich", "sanduche", "sanguche", "sánguche", "bocadillo"]
    es_palabra_sandwich = any(w in t_clean for w in variantes_sandwich)
    if es_palabra_sandwich:
        # Si es el producto fijo de la carta "Sandwich Mechada Palta" sin mencionar personalización ni pan
        if "mechada palta" in t_clean and not any(w in t_clean for w in ["armar", "arma", "personaliz", "pan", "frica", "ciabatta", "molde"]):
            return False

        verbos_sandwich = ["arma", "armar", "hazme", "hacer", "prepárame", "preparar", "quiero", "pídeme", "dame", "poner", "ponle", "con", "de"]
        if any(v in t_clean for v in verbos_sandwich):
            return True
        palabras_ingredientes = ["pan", "pollo", "mechada", "carne", "palta", "queso", "lomito", "tomate", "cebolla", "tocino", "mayo", "bbq", "frica", "ciabatta", "molde"]
        if any(p in t_clean for p in palabras_ingredientes):
            return True

    return False



def es_orden_sandwich_personalizado(texto: str) -> bool:
    """Detecta si el usuario está ORDENANDO armar un sandwich con ingredientes."""
    return es_intencion_sandwich_custom(texto)


def es_intencion_pago(texto: str) -> bool:
    """
    Detecta si el usuario desea pagar, terminar su pedido o solicita la cuenta.
    Ejemplos: 'ya termine mi pedido quiero pagar', 'quiero pagar', 'la cuenta por favor', 'cobrar'.
    """
    if not texto:
        return False
    t = texto.lower()
    t_clean = (
        t.replace("á", "a")
        .replace("é", "e")
        .replace("í", "i")
        .replace("ó", "o")
        .replace("ú", "u")
    )

    frases_pago = [
        "ya termine mi pedido quiero pagar",
        "ya termine mi pedido y quiero pagar",
        "ya termine mi pedido",
        "termine mi pedido quiero pagar",
        "termine mi pedido",
        "termine de pedir",
        "terminar mi pedido",
        "terminar el pedido",
        "terminar pedido",
        "quiero pagar",
        "quiero pagar mi pedido",
        "quiero pagar la cuenta",
        "quiero la cuenta",
        "la cuenta por favor",
        "la cuenta",
        "cobrar por favor",
        "cobrame",
        "cobrar",
        "pasar a pagar",
        "ir a pagar",
        "proceder al pago",
        "finalizar y pagar",
        "finalizar pedido",
        "finalizar el pedido",
        "finalizar mi pedido",
        "finalizar compra",
        "cerrar pedido",
        "cerrar la cuenta",
        "listo para pagar",
        "listo quiero pagar",
        "voy a pagar",
        "ya termine quiero pagar",
        "ya termine de pedir",
        "eso es todo quiero pagar",
        "eso seria todo quiero pagar",
        "ya esta quiero pagar",
        "pagar mi pedido",
        "pagar la cuenta",
        "pagar",
    ]
    if any(p in t_clean for p in frases_pago):
        return True

    tiene_pagar = any(w in t_clean for w in ["pagar", "pago", "cobrar", "cuenta"])
    tiene_fin = any(w in t_clean for w in ["termine", "terminar", "listo", "finalizar", "cerrar", "ya esta", "eso es todo", "eso seria"])
    if tiene_pagar and tiene_fin:
        return True

    return False


def producto_a_ofrecido(p: Producto, descripcion: str = "", es_combo: bool = False, ingredientes: list = None) -> Dict[str, Any]:
    """Convierte un modelo Producto a diccionario enriquecido para la interfaz del usuario."""
    return {
        "id": p.id,
        "nombre": p.nombre,
        "categoria": p.categoria,
        "precio": p.precio,
        "stock_disponible": p.stock_disponible,
        "imagen_url": p.imagen_url or "",
        "descripcion": descripcion or "",
        "es_combo_o_custom": es_combo,
        "ingredientes_sugeridos": ingredientes or [],
        "tipo_personalizado": getattr(p, "tipo_personalizado", "ninguno") or "ninguno",
        "es_vegetariano": bool(getattr(p, "es_vegetariano", 0)),
        "es_vegano": bool(getattr(p, "es_vegano", 0)),
    }


def item_custom_a_ofrecido(nombre: str, categoria: str, precio: int, descripcion: str, imagen_url: str, ingredientes: list, es_veg: bool = True, es_vegan: bool = True) -> Dict[str, Any]:
    """Crea una tarjeta de sandwich personalizado o combo sugerido para el usuario."""
    return {
        "id": 9999,
        "nombre": nombre,
        "categoria": categoria,
        "precio": precio,
        "stock_disponible": 99,
        "imagen_url": imagen_url,
        "descripcion": descripcion,
        "es_combo_o_custom": True,
        "ingredientes_sugeridos": ingredientes,
        "tipo_personalizado": "custom",
        "es_vegetariano": es_veg,
        "es_vegano": es_vegan,
    }


def generar_respuesta_consulta(mensaje: str, db: Session) -> Tuple[str, List[Dict[str, Any]]]:
    """
    Genera una respuesta inteligente con raciocinio real basada en los datos de SQLite y Ollama.
    Retorna la respuesta en texto para voz/chat Y la lista estructurada de productos sugeridos para mostrar en pantalla.
    NUNCA modifica el pedido ni descuenta inventario.
    """
    m = mensaje.lower().strip()
    productos_ofrecidos: List[Dict[str, Any]] = []

    # Prefijo de saludo si el cliente saludó
    saludo = ""
    if any(m.startswith(g) for g in ["hola", "buenos días", "buenas tardes", "buenas noches", "buenas"]):
        saludo = "¡Hola! "

    # 1. Saludo exclusivo (sin otra pregunta añadida)
    if m in ["hola", "buenas", "buenos días", "buenas tardes", "buenas noches", "hola buenas", "hola qué tal"]:
        prods = db.query(Producto).filter(
            Producto.nombre.in_(["Hamburguesa Clásica", "Papas Fritas Medianas", "Bebida Cola 350ml"]),
            getattr(Producto, "activo", 1) == 1
        ).all()
        productos_ofrecidos = [producto_a_ofrecido(p) for p in prods]
        return (
            "¡Hola! Bienvenido a Voice Bistro. Puedes consultarme precios, armar tu sandwich a tu gusto, o pedirme directamente lo que gustes.",
            productos_ofrecidos
        )

    # 2. Armar sandwich o consultar ingredientes: OBLIGAR A ESCOGER EL PAN PRIMERO
    if any(w in m for w in ["armar sandwich", "sandwich personalizado", "sánguche personalizado", "ingrediente", "ingredientes", "panes"]):
        panes_db = db.query(Producto).filter(
            (Producto.tipo_personalizado == "base") | (Producto.categoria == "Panes"),
            Producto.stock_disponible > 0,
            getattr(Producto, "activo", 1) == 1
        ).all()

        # En pantalla se muestran ÚNICAMENTE las bases disponibles (panes)
        productos_ofrecidos = [producto_a_ofrecido(p) for p in panes_db]
        panes_txt = ", ".join([f"{p.nombre} (${p.precio})" for p in panes_db])

        texto = (
            saludo + "Para armar tu sandwich personalizado es obligatorio elegir primero la base (pan). "
            f"Opciones disponibles: {panes_txt}. "
            "¿Cuál pan prefieres? Elige uno en pantalla o dímelo por voz y luego te mostraré todos los ingredientes."
        )
        return texto, productos_ofrecidos

    # 3. Opciones vegetarianas y veganas
    if any(w in m for w in ["vegetariano", "vegetariana", "vegetarianos", "vegetarianas", "vegano", "vegana", "veganos", "veganas", "sin carne", "plant based"]):
        es_vegano_query = any(w in m for w in ["vegano", "vegana", "veganos", "veganas"])
        filtro = (Producto.es_vegano == 1) if es_vegano_query else (Producto.es_vegetariano == 1)
        items_veg = db.query(Producto).filter(
            filtro,
            Producto.stock_disponible > 0,
            getattr(Producto, "activo", 1) == 1
        ).all()
        productos_ofrecidos = [producto_a_ofrecido(p) for p in items_veg]
        tipo_label = "veganas" if es_vegano_query else "vegetarianas"
        nombres_destacados = [p.nombre for p in items_veg[:5]]
        texto = (
            saludo + f"¡Sí! Tenemos varias opciones {tipo_label} disponibles ({', '.join(nombres_destacados)}). "
            f"Además puedes armar tu sándwich 100% {tipo_label} eligiendo pan y agregados como palta, champiñones, tomate y cebolla caramelizada."
        )
        return texto, productos_ofrecidos

    # 4. Salsas y aderezos
    if any(w in m for w in ["salsa", "salsas", "aderezo", "aderezos"]):
        salsas_db = db.query(Producto).filter(Producto.categoria == "Salsas", Producto.stock_disponible > 0, getattr(Producto, "activo", 1) == 1).all()
        productos_ofrecidos = [producto_a_ofrecido(p) for p in salsas_db]
        salsas_txt = ", ".join([f"{p.nombre} (${p.precio})" for p in salsas_db])
        return saludo + f"En salsas y aderezos disponemos de: {salsas_txt}.", productos_ofrecidos

    # 5. Sandwiches en general
    if any(w in m for w in ["sandwich", "sandwiches", "sánguche", "sanguche"]):
        sandwiches_db = db.query(Producto).filter(
            (Producto.nombre.ilike("%sandwich%") | Producto.nombre.ilike("%hamburguesa%")),
            Producto.nombre != "Sandwich Personalizado",
            Producto.stock_disponible > 0,
            getattr(Producto, "activo", 1) == 1
        ).all()
        productos_ofrecidos = [producto_a_ofrecido(p) for p in sandwiches_db]

        # Sugerir sandwich personalizado
        custom_sandwich = item_custom_a_ofrecido(
            nombre="Sandwich Personalizado a tu Gusto",
            categoria="Sandwiches Custom",
            precio=5700,
            descripcion="Elige tu pan, carne, agregados y salsas favoritas",
            imagen_url="https://images.unsplash.com/photo-1528735602780-2552fd46c7af?w=500&auto=format&fit=crop&q=80",
            ingredientes=["Pan Ciabatta Rústico", "Carne Mechada Casera", "Palta Hass Molida", "Mayonesa Casera"]
        )
        productos_ofrecidos.append(custom_sandwich)

        sandwiches_list = ", ".join([f"{p.nombre} (${p.precio})" for p in sandwiches_db])
        sandwiches_txt = f"opciones preparadas como {sandwiches_list}." if sandwiches_list else "opciones para armar a tu gusto."
        texto = (
            saludo + f"En sandwiches tenemos {sandwiches_txt} "
            "Además, puedes armar tu propio sandwich a medida combinando panes, carnes y agregados frescos."
        )
        return texto, productos_ofrecidos

    # 6. Bebidas
    if any(w in m for w in ["bebida", "tomar", "refresco", "gaseosa", "jugo"]):
        bebidas_disp = db.query(Producto).filter(Producto.categoria == "Bebidas", getattr(Producto, "activo", 1) == 1).all()
        productos_ofrecidos = [producto_a_ofrecido(p) for p in bebidas_disp]

        disponibles = [f"{p.nombre} (${p.precio})" for p in bebidas_disp if p.stock_disponible > 0]
        agotadas = [p.nombre for p in bebidas_disp if p.stock_disponible <= 0]
        info = saludo + f"De bebidas tenemos disponibles: {', '.join(disponibles)}."
        if agotadas:
            info += f" Ten en cuenta que {', '.join(agotadas)} está temporalmente agotado."
        return info, productos_ofrecidos

    # 7. Postres y Cafetería
    if any(w in m for w in ["postre", "postres", "dulce", "dulces", "café", "cafe", "cafeteria", "cafetería"]):
        items_db = db.query(Producto).filter(Producto.categoria.in_(["Postres", "Cafetería"]), getattr(Producto, "activo", 1) == 1).all()
        productos_ofrecidos = [producto_a_ofrecido(p) for p in items_db]
        items_txt = ", ".join([f"{p.nombre} (${p.precio})" for p in items_db if p.stock_disponible > 0])
        return saludo + f"En cafetería y postres tenemos: {items_txt}.", productos_ofrecidos

    # 8. Acompañamientos / Papas
    if any(w in m for w in ["papas", "acompañamiento", "aros"]):
        acomps_db = db.query(Producto).filter(Producto.categoria == "Acompañamientos", getattr(Producto, "activo", 1) == 1).all()
        productos_ofrecidos = [producto_a_ofrecido(p) for p in acomps_db]
        papas_disp = ", ".join([f"{p.nombre} (${p.precio})" for p in acomps_db if p.stock_disponible > 0])
        return saludo + f"De acompañamientos tenemos disponibles: {papas_disp}.", productos_ofrecidos

    # 9. Más barato / Más caro
    if any(w in m for w in ["barato", "económico", "economico"]):
        barato = db.query(Producto).filter(Producto.stock_disponible > 0, Producto.precio > 0, Producto.categoria.in_(["Comidas", "Acompañamientos", "Bebidas", "Postres"])).order_by(Producto.precio.asc()).first()
        if barato:
            productos_ofrecidos.append(producto_a_ofrecido(barato, "Opción más económica de la carta"))
            return saludo + f"Lo más económico disponible en nuestro menú es {barato.nombre} a solo ${barato.precio} CLP.", productos_ofrecidos

    if any(w in m for w in ["caro", "premium", "especial"]):
        caro = db.query(Producto).filter(Producto.stock_disponible > 0, Producto.precio > 0, Producto.categoria.in_(["Comidas", "Acompañamientos", "Bebidas", "Postres"])).order_by(Producto.precio.desc()).first()
        if caro:
            productos_ofrecidos.append(producto_a_ofrecido(caro, "Nuestra especialidad más completa"))
            return saludo + f"Nuestra opción más completa es {caro.nombre} por ${caro.precio} CLP.", productos_ofrecidos

    # 10. Preguntas de precio o stock de un producto específico
    for p in db.query(Producto).all():
        if len(p.nombre) > 4:
            palabras_prod = [w.lower() for w in p.nombre.split() if len(w) > 4]
            if palabras_prod and any(w in m for w in palabras_prod):
                productos_ofrecidos.append(producto_a_ofrecido(p))
                # Sugerir papas y bebida para acompañar
                extras = db.query(Producto).filter(Producto.nombre.in_(["Papas Fritas Medianas", "Bebida Cola 350ml"]), Producto.stock_disponible > 0).all()
                for extra in extras:
                    productos_ofrecidos.append(producto_a_ofrecido(extra, "Ideal para acompañar tu orden"))

                if p.stock_disponible <= 0:
                    sustitutos = db.query(Producto).filter(Producto.categoria == p.categoria, Producto.stock_disponible > 0, Producto.id != p.id).all()
                    if sustitutos:
                        productos_ofrecidos.insert(1, producto_a_ofrecido(sustitutos[0], "Sustituto disponible recomendado"))
                    sust_texto = f", pero te recomiendo {sustitutos[0].nombre} (${sustitutos[0].precio} CLP)" if sustitutos else ""
                    return saludo + f"El producto {p.nombre} cuesta ${p.precio} CLP pero lamentablemente está AGOTADO (stock 0){sust_texto}.", productos_ofrecidos
                else:
                    return saludo + f"{p.nombre} tiene un valor de ${p.precio} CLP y cuenta con {p.stock_disponible} unidades en stock.", productos_ofrecidos

    # 11. Recomendaciones
    if any(w in m for w in ["recomienda", "recomiendas", "rico", "sugieres", "sugerencia", "almorzar", "comer", "hambre"]):
        combo_prods = db.query(Producto).filter(
            Producto.nombre.in_(["Hamburguesa Clásica", "Papas Fritas Medianas", "Bebida Cola 350ml", "Sandwich Mechada Palta"]),
            Producto.stock_disponible > 0
        ).all()
        productos_ofrecidos = [producto_a_ofrecido(p) for p in combo_prods]
        return (
            saludo + "Te recomiendo nuestra Hamburguesa Clásica con Papas Fritas y Bebida Cola, o un sabroso Sandwich Mechada Palta. ¡Aquí los tienes en pantalla!",
            productos_ofrecidos
        )

    # 12. Raciocinio con Ollama grounded en la BD local para preguntas abiertas
    try:
        menu_items = db.query(Producto).filter(Producto.stock_disponible > 0).all()
        menu_str = ", ".join([f"{p.nombre} (${p.precio})" for p in menu_items[:12]])
        prompt_consulta = (
            f"El cliente hace esta pregunta o comentario: '{mensaje}'.\n"
            f"Menú disponible en el restaurante: {menu_str}.\n"
            "Responde de forma concisa, educada y apetitosa en español (máximo 2 oraciones). "
            "NO digas que agregaste nada al pedido, ya que esto es una consulta informativa."
        )
        resp = openai_client.chat.completions.create(
            model=MODEL_NAME,
            messages=[
                {"role": "system", "content": "Eres el anfitrión servicial de Voice Bistro. Responde consultas con cortesía y claridad."},
                {"role": "user", "content": prompt_consulta}
            ],
            temperature=0.3,
            max_tokens=120
        )
        texto_llm = resp.choices[0].message.content.strip()

        # Encontrar productos mencionados en el texto del LLM
        for item in menu_items:
            partes = [pt.lower() for pt in item.nombre.split() if len(pt) > 4]
            if any(pt in texto_llm.lower() for pt in partes) and len(productos_ofrecidos) < 4:
                productos_ofrecidos.append(producto_a_ofrecido(item))

        if not productos_ofrecidos:
            productos_ofrecidos = [producto_a_ofrecido(p) for p in menu_items[:4]]

        return texto_llm, productos_ofrecidos
    except Exception as e:
        logger.warning(f"Error consultando Ollama para respuesta general: {e}")

    # Fallback general si Ollama no respondiera
    destacados_db = db.query(Producto).filter(Producto.stock_disponible > 0, Producto.categoria.in_(["Comidas", "Acompañamientos", "Bebidas"])).limit(4).all()
    productos_ofrecidos = [producto_a_ofrecido(p) for p in destacados_db]
    destacados = ", ".join([f"{p.nombre} (${p.precio})" for p in destacados_db])
    return saludo + f"Tenemos en nuestro menú: {destacados}. ¿Te gustaría ordenar algo o consultar más detalles?", productos_ofrecidos


def identificar_ingredientes_en_texto(db: Session, texto: str) -> List[Producto]:
    """Identifica qué ingredientes del catálogo fueron mencionados en el texto del usuario."""
    categorias_ingredientes = ["Panes", "Proteínas", "Agregados", "Salsas"]
    ingredientes_bd = db.query(Producto).filter(
        (Producto.categoria.in_(categorias_ingredientes)) | (Producto.tipo_personalizado.in_(["base", "ingrediente"])),
        getattr(Producto, "activo", 1) == 1
    ).all()

    encontrados = []
    texto_l = texto.lower()
    nombres_agregados = set()

    # Mapeo de términos ordenados por especificidad (más específicos primero)
    sinonimos_especificos = [
        ("carne de hamburguesa", "Hamburguesa de Res"),
        ("hamburguesa de res", "Hamburguesa de Res"),
        ("hamburguesa", "Hamburguesa de Res"),
        ("carne mechada", "Carne Mechada Casera"),
        ("mechada", "Carne Mechada Casera"),
        ("deshilachada", "Carne Mechada Casera"),
        ("carne", "Carne Mechada Casera"),
        ("pollo a la plancha", "Pollo a la Plancha"),
        ("pollo", "Pollo a la Plancha"),
        ("pechuga", "Pollo a la Plancha"),
        ("pollito", "Pollo a la Plancha"),
        ("lomito de cerdo", "Lomito de Cerdo"),
        ("lomito", "Lomito de Cerdo"),
        ("cerdo", "Lomito de Cerdo"),
        ("chancho", "Lomito de Cerdo"),
        ("palta hass", "Palta Hass Molida"),
        ("palta", "Palta Hass Molida"),
        ("aguacate", "Palta Hass Molida"),
        ("guacamole", "Palta Hass Molida"),
        ("queso cheddar", "Queso Cheddar Fundido"),
        ("cheddar", "Queso Cheddar Fundido"),
        ("queso gauda", "Queso Gauda Fundido"),
        ("gauda", "Queso Gauda Fundido"),
        ("queso", "Queso Gauda Fundido"),
        ("tomate en rodajas", "Tomate en Rodajas"),
        ("tomates", "Tomate en Rodajas"),
        ("tomate", "Tomate en Rodajas"),
        ("cebolla caramelizada", "Cebolla Caramelizada"),
        ("cebolla", "Cebolla Caramelizada"),
        ("champiñones salteados", "Champiñones Salteados"),
        ("champinones salteados", "Champiñones Salteados"),
        ("champiñones", "Champiñones Salteados"),
        ("champinones", "Champiñones Salteados"),
        ("champiñon", "Champiñones Salteados"),
        ("hongos", "Champiñones Salteados"),
        ("tocino crocante", "Tocino Crocante"),
        ("tocino", "Tocino Crocante"),
        ("bacon", "Tocino Crocante"),
        ("panceta", "Tocino Crocante"),
        ("mayonesa casera", "Mayonesa Casera"),
        ("mayonesa", "Mayonesa Casera"),
        ("mayo", "Mayonesa Casera"),
        ("salsa bbq", "Salsa BBQ Ahumada"),
        ("bbq", "Salsa BBQ Ahumada"),
        ("barbacoa", "Salsa BBQ Ahumada"),
        ("salsa verde", "Salsa Verde Cilantro"),
        ("verde cilantro", "Salsa Verde Cilantro"),
        ("cilantro", "Salsa Verde Cilantro"),
        # Panes
        ("pan frica", "Pan Frica Artesanal"),
        ("frica", "Pan Frica Artesanal"),
        ("pan ciabatta", "Pan Ciabatta Rústico"),
        ("ciabatta", "Pan Ciabatta Rústico"),
        ("ciabata", "Pan Ciabatta Rústico"),
        ("pan de molde", "Pan de Molde Integral"),
        ("de molde", "Pan de Molde Integral"),
        ("integral", "Pan de Molde Integral"),
    ]

    for clave, nombre_canonico in sinonimos_especificos:
        if clave in texto_l and nombre_canonico not in nombres_agregados:
            ing = next((p for p in ingredientes_bd if p.nombre.lower() == nombre_canonico.lower()), None)
            if ing:
                encontrados.append(ing)
                nombres_agregados.add(nombre_canonico)
                texto_l = texto_l.replace(clave, " " * len(clave))

    return encontrados


def identificar_base_en_texto(db: Session, texto: str) -> Optional[Producto]:
    """Identifica si el usuario seleccionó o mencionó una base (pan) para su sandwich."""
    if not texto:
        return None
    texto_l = texto.lower().strip()
    bases_bd = db.query(Producto).filter(
        (Producto.tipo_personalizado == "base") | (Producto.categoria == "Panes"),
        getattr(Producto, "activo", 1) == 1
    ).all()

    if not bases_bd:
        return None

    # Mapeo por posiciones / ordinales cuando el bot ofrece las opciones:
    # 1: Pan Frica Artesanal, 2: Pan Ciabatta Rústico, 3: Pan de Molde Integral
    patrones_ordinales = {
        0: ["primero", "primer", "primera", "el 1", "la 1", "opcion 1", "opción 1", "número 1", "numero 1", "uno"],
        1: ["segundo", "segunda", "el 2", "la 2", "opcion 2", "opción 2", "número 2", "numero 2", "dos"],
        2: ["tercero", "tercer", "tercera", "el 3", "la 3", "opcion 3", "opción 3", "número 3", "numero 3", "tres", "ultimo", "último"],
    }
    for idx, palabras in patrones_ordinales.items():
        if idx < len(bases_bd):
            if any(p in texto_l for p in palabras):
                # Descartar si solo es cantidad de un producto diferente
                if not any(w in texto_l for w in ["papas", "hamburguesas", "bebidas", "aros", "empanadas"]):
                    return bases_bd[idx]

    # Mapeo de sinónimos y variantes fonéticas/coloquiales
    sinonimos_base = {
        "frica": "Pan Frica Artesanal",
        "fricas": "Pan Frica Artesanal",
        "artesanal": "Pan Frica Artesanal",
        "ciabatta": "Pan Ciabatta Rústico",
        "ciabata": "Pan Ciabatta Rústico",
        "chabata": "Pan Ciabatta Rústico",
        "chiavata": "Pan Ciabatta Rústico",
        "rustico": "Pan Ciabatta Rústico",
        "rústico": "Pan Ciabatta Rústico",
        "baguette": "Pan Ciabatta Rústico",
        "italiano": "Pan Ciabatta Rústico",
        "molde": "Pan de Molde Integral",
        "integral": "Pan de Molde Integral",
        "integrales": "Pan de Molde Integral",
        "negro": "Pan de Molde Integral",
        "marraqueta": "Pan de Molde Integral",
        "blanco": "Pan Frica Artesanal",
        "normal": "Pan Frica Artesanal",
        "tradicional": "Pan Frica Artesanal",
        "cualquiera": "Pan Frica Artesanal",
        "el mejor": "Pan Frica Artesanal",
    }
    for clave, nombre_canonico in sinonimos_base.items():
        if clave in texto_l:
            p = next((b for b in bases_bd if b.nombre.lower() == nombre_canonico.lower()), None)
            if p:
                return p

    # Búsqueda directa por palabras clave en el nombre del producto
    for b in bases_bd:
        partes = [p.lower() for p in b.nombre.split() if len(p) > 3 and p.lower() != "artesanal"]
        if any(p in texto_l for p in partes):
            return b

    return None


def identificar_ingredientes_adicionales_en_texto(db: Session, texto: str) -> List[Producto]:
    """Identifica ingredientes mencionados que correspondan a agregados/carnes/salsas (no bases)."""
    todos = identificar_ingredientes_en_texto(db, texto)
    return [
        p for p in todos 
        if getattr(p, "tipo_personalizado", "ninguno") != "base" and p.categoria != "Panes"
    ]


# ==========================================
# LÓGICA DE TOOLS / HERRAMIENTAS SQLITE
# ==========================================
def tool_consultar_inventario(db: Session, termino_busqueda: str) -> Dict[str, Any]:
    """Busca productos o ingredientes por nombre o categoría en SQLite."""
    termino = (termino_busqueda or "").strip()

    if not termino or termino.lower() in ["todo", "menu", "carta", "catalogo", "ingredientes", "sandwich"]:
        productos = db.query(Producto).all()
    else:
        patron = f"%{termino}%"
        productos = db.query(Producto).filter(
            Producto.nombre.ilike(patron) | Producto.categoria.ilike(patron)
        ).all()

        if not productos and " " in termino:
            palabras = [p for p in termino.split() if len(p) > 2]
            if palabras:
                condiciones = [Producto.nombre.ilike(f"%{p}%") for p in palabras]
                productos = db.query(Producto).filter(*condiciones).all()

    items_res = []
    for p in productos:
        item = {
            "id": p.id,
            "nombre": p.nombre,
            "categoria": p.categoria,
            "precio": p.precio,
            "stock_disponible": p.stock_disponible,
            "agotado": p.stock_disponible <= 0,
        }
        if p.stock_disponible <= 0:
            sustitutos = db.query(Producto).filter(
                Producto.categoria == p.categoria,
                Producto.stock_disponible > 0,
                Producto.id != p.id
            ).all()
            item["sustitutos"] = [f"{s.nombre} (${s.precio})" for s in sustitutos]
        items_res.append(item)

    return {
        "termino_buscado": termino,
        "total_encontrados": len(items_res),
        "productos": items_res,
    }


def tool_agregar_al_pedido(db: Session, session_id: str, producto_id: Any, cantidad: Any, texto_contexto: str = "") -> Dict[str, Any]:
    """Valida stock, descuenta y asocia producto al pedido de la sesión en SQLite."""
    try:
        p_id = int(producto_id)
        cant = max(1, int(cantidad))
    except (ValueError, TypeError):
        p_id = 0
        cant = 1

    producto = db.query(Producto).filter(Producto.id == p_id).first() if p_id > 0 else None

    # Si el ID no existe o no corresponde al producto nombrado por el usuario en texto_contexto:
    if texto_contexto:
        for prod in db.query(Producto).all():
            partes = [p.lower() for p in prod.nombre.split() if len(p) > 3 and "350" not in p and "250" not in p]
            if any(p in texto_contexto.lower() for p in partes):
                producto = prod
                break

    # Si la cantidad es absurdamente alta (ej: 350 por 350ml), usar la cantidad extraída del texto
    if cant > 15 and texto_contexto:
        cant_extraida = extraer_cantidad_desde_texto(texto_contexto)
        if cant_extraida <= 15:
            cant = cant_extraida

    if not producto:
        return {"exito": False, "mensaje": "Producto no encontrado en inventario."}

    if getattr(producto, "activo", 1) == 0:
        return {
            "exito": False,
            "motivo": "DESACTIVADO",
            "producto": producto.nombre,
            "mensaje": f"El producto '{producto.nombre}' se encuentra temporalmente desactivado de la carta.",
        }

    # Si el producto es un ingrediente de sandwich, debe ir DENTRO del sandwich personalizado
    if getattr(producto, "tipo_personalizado", "ninguno") == "ingrediente" or producto.categoria in ["Proteínas", "Agregados", "Salsas"]:
        pedido_existente = db.query(Pedido).filter(Pedido.session_id == session_id, Pedido.estado == "en_proceso").first()
        ultimo_sw = None
        if pedido_existente:
            for d in reversed(pedido_existente.detalles):
                if (d.producto and d.producto.nombre == "Sandwich Personalizado") or (d.descripcion_adicional and d.descripcion_adicional.startswith("🥖")):
                    ultimo_sw = d
                    break
        if ultimo_sw:
            return tool_agregar_ingrediente_a_sandwich_existente(db, session_id, [producto.id], detalle_id=ultimo_sw.id)
        else:
            return {
                "exito": False,
                "motivo": "INGREDIENTE_REQUIERE_BASE",
                "producto": producto.nombre,
                "mensaje": f"El producto '{producto.nombre}' es un ingrediente. Para pedirlo, primero debes elegir el pan (base obligatoria): 1) Pan Frica Artesanal, 2) Pan Ciabatta Rústico o 3) Pan de Molde Integral.",
            }

    # Flujo de agotados
    if producto.stock_disponible <= 0:
        sustitutos = db.query(Producto).filter(
            Producto.categoria == producto.categoria,
            Producto.stock_disponible > 0,
            Producto.id != producto.id
        ).all()
        sust_str = ", ".join([f"{s.nombre} (${s.precio})" for s in sustitutos]) if sustitutos else "ninguno"
        return {
            "exito": False,
            "motivo": "AGOTADO",
            "producto": producto.nombre,
            "categoria": producto.categoria,
            "stock": 0,
            "sustitutos_disponibles": [s.nombre for s in sustitutos],
            "mensaje": f"El producto '{producto.nombre}' está agotado (stock 0). Sugerir sustitutos de {producto.categoria}: {sust_str}.",
        }

    # Flujo de stock insuficiente
    if cant > producto.stock_disponible:
        return {
            "exito": False,
            "motivo": "STOCK_INSUFICIENTE",
            "producto": producto.nombre,
            "stock_disponible": producto.stock_disponible,
            "mensaje": f"Stock insuficiente para '{producto.nombre}'. Solo quedan {producto.stock_disponible} unidades disponibles.",
        }

    # Buscar o crear pedido
    pedido = db.query(Pedido).filter(Pedido.session_id == session_id, Pedido.estado == "en_proceso").first()
    if not pedido:
        pedido = Pedido(session_id=session_id, total=0, estado="en_proceso")
        db.add(pedido)
        db.flush()

    # Descontar stock disponible en SQLite
    producto.stock_disponible -= cant

    # Buscar o crear DetallePedido
    detalle = db.query(DetallePedido).filter(
        DetallePedido.pedido_id == pedido.id,
        DetallePedido.producto_id == producto.id,
    ).first()

    if detalle:
        detalle.cantidad += cant
        detalle.subtotal = detalle.cantidad * detalle.precio_unitario
    else:
        detalle = DetallePedido(
            pedido_id=pedido.id,
            producto_id=producto.id,
            cantidad=cant,
            precio_unitario=producto.precio,
            subtotal=cant * producto.precio,
        )
        db.add(detalle)

    db.flush()
    pedido.total = sum(d.subtotal for d in pedido.detalles)
    db.commit()

    return {
        "exito": True,
        "producto": producto.nombre,
        "categoria": producto.categoria,
        "cantidad": cant,
        "precio_unitario": producto.precio,
        "subtotal": detalle.subtotal,
        "total_pedido": pedido.total,
        "stock_restante": producto.stock_disponible,
        "mensaje": f"Se agregó {cant}x {producto.nombre} exitosamente por ${detalle.subtotal}. Total acumulado del pedido: ${pedido.total}."
    }


def tool_armar_sandwich_personalizado(db: Session, session_id: str, ingredientes_ids: List[Any], texto_contexto: str = "") -> Dict[str, Any]:
    """
    Arma un sandwich customizado combinando múltiples ingredientes con control de stock individual en SQLite.
    Verifica que cada ingrediente tenga stock > 0. Si alguno está agotado, avisa y ofrece sustituto.
    """
    # Si la lista de IDs viene vacía o con datos erróneos, intentar extraer ingredientes desde el texto
    ingredientes_seleccionados: List[Producto] = []
    
    if ingredientes_ids:
        for item_id in ingredientes_ids:
            try:
                i_id = int(item_id)
                prod = db.query(Producto).filter(Producto.id == i_id).first()
                if prod:
                    ingredientes_seleccionados.append(prod)
            except (ValueError, TypeError):
                pass

    # Si no se encontraron suficientes por ID, extraer por nombres en texto_contexto
    if len(ingredientes_seleccionados) < 2 and texto_contexto:
        extraidos = identificar_ingredientes_en_texto(db, texto_contexto)
        if extraidos:
            ingredientes_seleccionados = extraidos

    if not ingredientes_seleccionados:
        return {
            "exito": False,
            "motivo": "SIN_INGREDIENTES",
            "mensaje": "No se identificaron ingredientes válidos para armar el sandwich. Por favor especifica el pan, proteína y agregados deseados.",
        }

    # 0. Validar obligatoriedad de la base (pan)
    bases_encontradas = [
        p for p in ingredientes_seleccionados 
        if getattr(p, "tipo_personalizado", "ninguno") == "base" or p.categoria == "Panes"
    ]
    if not bases_encontradas:
        bases_disp = db.query(Producto).filter(
            (Producto.tipo_personalizado == "base") | (Producto.categoria == "Panes"),
            Producto.stock_disponible > 0,
            getattr(Producto, "activo", 1) == 1
        ).all()
        nombres_bases = [f"{b.nombre} (${b.precio})" for b in bases_disp]
        return {
            "exito": False,
            "motivo": "FALTA_BASE",
            "mensaje": f"Para armar tu sandwich personalizado es obligatorio elegir primero el pan (base). Opciones disponibles: {', '.join(nombres_bases)}.",
            "bases_disponibles": [b.to_dict() for b in bases_disp],
            "ingredientes_sin_base": [p.id for p in ingredientes_seleccionados],
        }

    # 1. Validar si ALGÚN ingrediente está AGOTADO (stock 0)
    for ing in ingredientes_seleccionados:
        if ing.stock_disponible <= 0:
            sustitutos = db.query(Producto).filter(
                Producto.categoria == ing.categoria,
                Producto.stock_disponible > 0,
                Producto.id != ing.id
            ).all()
            sust_nombres = [f"{s.nombre} (${s.precio})" for s in sustitutos]
            sust_sug = sust_nombres[0] if sust_nombres else "otra opción"
            return {
                "exito": False,
                "motivo": "AGOTADO",
                "ingrediente_agotado": ing.nombre,
                "categoria": ing.categoria,
                "sustitutos_disponibles": sust_nombres,
                "mensaje": f"El ingrediente '{ing.nombre}' está agotado (stock 0). Comunica esto amablemente y ofrece de sustituto de la categoría {ing.categoria}: {sust_sug}.",
            }

    # 2. Todos los ingredientes tienen stock disponible: Proceder con el descuento y armado
    # Garantizar que la base esté siempre primero en la descripción
    base_prod = bases_encontradas[0]
    otros_ings = [p for p in ingredientes_seleccionados if p.id != base_prod.id]
    desglose_nombres = [base_prod.nombre] + [ing.nombre for ing in otros_ings]
    precio_total_sandwich = 0

    for ing in ingredientes_seleccionados:
        ing.stock_disponible -= 1
        precio_total_sandwich += ing.precio

    if otros_ings:
        descripcion_sandwich = f"🥖 {base_prod.nombre} + " + " + ".join(ing.nombre for ing in otros_ings)
    else:
        descripcion_sandwich = f"🥖 {base_prod.nombre}"

    # Buscar o crear producto base de sandwich custom
    prod_custom = db.query(Producto).filter(Producto.categoria == "Sandwiches Custom").first()
    if not prod_custom:
        prod_custom = Producto(nombre="Sandwich Personalizado", categoria="Sandwiches Custom", precio=0, stock_disponible=999)
        db.add(prod_custom)
        db.flush()

    # Buscar o crear pedido
    pedido = db.query(Pedido).filter(Pedido.session_id == session_id, Pedido.estado == "en_proceso").first()
    if not pedido:
        pedido = Pedido(session_id=session_id, total=0, estado="en_proceso")
        db.add(pedido)
        db.flush()

    # Crear DetallePedido para el sandwich personalizado
    detalle = DetallePedido(
        pedido_id=pedido.id,
        producto_id=prod_custom.id,
        cantidad=1,
        precio_unitario=precio_total_sandwich,
        subtotal=precio_total_sandwich,
        descripcion_adicional=descripcion_sandwich,
    )
    db.add(detalle)
    db.flush()

    pedido.total = sum(d.subtotal for d in pedido.detalles)
    db.commit()

    return {
        "exito": True,
        "detalle_id": detalle.id,
        "nombre": "Sandwich Personalizado",
        "descripcion": descripcion_sandwich,
        "ingredientes_totales": len(ingredientes_seleccionados),
        "precio_sandwich": precio_total_sandwich,
        "total_pedido": pedido.total,
        "mensaje": f"Sandwich personalizado armado con éxito ({descripcion_sandwich}) por ${precio_total_sandwich}. Total del pedido: ${pedido.total}."
    }


def tool_agregar_ingrediente_a_sandwich_existente(db: Session, session_id: str, ingredientes_ids: List[Any], detalle_id: Optional[int] = None) -> Dict[str, Any]:
    """
    Agrega ingredientes adicionales a un sandwich personalizado ya existente en el pedido.
    Descuenta inventario en SQLite, actualiza precio y concatena los nuevos ingredientes a la descripción.
    """
    pedido = db.query(Pedido).filter(Pedido.session_id == session_id, Pedido.estado == "en_proceso").first()
    if not pedido:
        return {"exito": False, "motivo": "SIN_PEDIDO", "mensaje": "No hay un pedido activo para esta sesión."}

    # Buscar el detalle del sandwich personalizado
    detalle = None
    if detalle_id:
        detalle = db.query(DetallePedido).filter(DetallePedido.id == detalle_id, DetallePedido.pedido_id == pedido.id).first()

    if not detalle:
        for d in reversed(pedido.detalles):
            if (d.producto and d.producto.nombre == "Sandwich Personalizado") or (d.descripcion_adicional and d.descripcion_adicional.startswith("🥖")):
                detalle = d
                break

    if not detalle:
        return {"exito": False, "motivo": "SIN_SANDWICH", "mensaje": "No se encontró un sandwich personalizado en el pedido para agregar ingredientes."}

    nuevos_ings: List[Producto] = []
    for item_id in ingredientes_ids:
        try:
            i_id = int(item_id)
            prod = db.query(Producto).filter(Producto.id == i_id).first()
            if prod:
                nuevos_ings.append(prod)
        except (ValueError, TypeError):
            pass

    if not nuevos_ings:
        return {"exito": False, "motivo": "SIN_INGREDIENTES", "mensaje": "No se reconocieron ingredientes válidos para añadir."}

    # Validar stock disponible
    for ing in nuevos_ings:
        if ing.stock_disponible <= 0:
            sustitutos = db.query(Producto).filter(
                Producto.categoria == ing.categoria,
                Producto.stock_disponible > 0,
                Producto.id != ing.id
            ).all()
            sust_nombres = [f"{s.nombre} (${s.precio})" for s in sustitutos]
            return {
                "exito": False,
                "motivo": "AGOTADO",
                "ingrediente_agotado": ing.nombre,
                "sustitutos_disponibles": sust_nombres,
                "mensaje": f"El ingrediente '{ing.nombre}' está agotado (stock 0).",
            }

    # Descontar stock y actualizar detalle del sandwich
    nombres_agregados = []
    for ing in nuevos_ings:
        ing.stock_disponible -= 1
        detalle.precio_unitario += ing.precio
        nombres_agregados.append(ing.nombre)

    detalle.subtotal = detalle.precio_unitario * detalle.cantidad
    if detalle.descripcion_adicional:
        detalle.descripcion_adicional += " + " + " + ".join(nombres_agregados)
    else:
        detalle.descripcion_adicional = "🥖 Sandwich + " + " + ".join(nombres_agregados)

    pedido.total = sum(d.subtotal for d in pedido.detalles)
    db.commit()

    return {
        "exito": True,
        "detalle_id": detalle.id,
        "descripcion": detalle.descripcion_adicional,
        "ingredientes_agregados": nombres_agregados,
        "precio_sandwich": detalle.precio_unitario,
        "total_pedido": pedido.total,
        "mensaje": f"Agregué {' y '.join(nombres_agregados)} a tu sandwich personalizado ({detalle.descripcion_adicional}) por ${detalle.precio_unitario}. Total pedido: ${pedido.total}."
    }


# ==========================================
# ESQUEMAS PYDANTIC
# ==========================================
class ChatRequest(BaseModel):
    mensaje: str = Field(..., description="Mensaje de voz o texto enviado por el cliente.")
    session_id: str = Field(..., description="Identificador único de sesión.")


class ItemPedido(BaseModel):
    id: int
    producto_id: int
    nombre: str
    categoria: str
    cantidad: int
    precio_unitario: int
    subtotal: int
    descripcion_adicional: Optional[str] = ""


class PedidoActual(BaseModel):
    id: Optional[int] = None
    session_id: str
    total: int = 0
    estado: str = "en_proceso"
    items: List[ItemPedido] = []


class ProductoOfrecido(BaseModel):
    id: Optional[int] = None
    nombre: str
    categoria: str
    precio: int
    stock_disponible: int
    imagen_url: Optional[str] = ""
    descripcion: Optional[str] = ""
    es_combo_o_custom: bool = False
    ingredientes_sugeridos: Optional[List[str]] = []
    tipo_personalizado: Optional[str] = "ninguno"
    es_vegetariano: bool = False
    es_vegano: bool = False


class ChatResponse(BaseModel):
    respuesta_texto: str
    pedido_actual: PedidoActual
    productos_ofrecidos: List[ProductoOfrecido] = []
    mostrar_pago: bool = False


class ProductoCreate(BaseModel):
    nombre: str
    categoria: str
    precio: int
    stock_disponible: int
    imagen_url: Optional[str] = ""
    activo: Optional[bool] = True
    tipo_personalizado: Optional[str] = "ninguno"
    es_vegetariano: Optional[bool] = False
    es_vegano: Optional[bool] = False


class ProductoUpdate(BaseModel):
    nombre: Optional[str] = None
    categoria: Optional[str] = None
    precio: Optional[int] = None
    stock_disponible: Optional[int] = None
    imagen_url: Optional[str] = None
    activo: Optional[bool] = None
    tipo_personalizado: Optional[str] = None
    es_vegetariano: Optional[bool] = None
    es_vegano: Optional[bool] = None


class ArmarSandwichDirectoRequest(BaseModel):
    base_id: int
    ingredientes_ids: List[int] = []


class EstadoUpdate(BaseModel):
    activo: Optional[bool] = None


class StockUpdate(BaseModel):
    stock_disponible: int


class PrecioUpdate(BaseModel):
    precio: int


# ==========================================
# ENDPOINT PRINCIPAL: /api/chat-pedido
# ==========================================
@app.post("/api/chat-pedido", response_model=ChatResponse)
async def chat_pedido(request: ChatRequest, db: Session = Depends(get_db)):
    """
    Endpoint principal:
    Recibe el mensaje de voz/texto del cliente, ejecuta el ciclo completo de Tool Calling
    con Ollama (llama3.2:1b) y SQLite, incluyendo sandwiches personalizados y control de stock.
    Retorna la respuesta de voz/texto, el ticket del pedido y los productos ofrecidos para mostrar en pantalla.
    """
    session_id = request.session_id.strip()
    mensaje_usuario = request.mensaje.strip()

    if not mensaje_usuario:
        raise HTTPException(status_code=400, detail="El mensaje no puede estar vacío.")

    if session_id not in session_histories:
        session_histories[session_id] = []

    historial = session_histories[session_id]
    if len(historial) > 8:
        historial = historial[-8:]
        session_histories[session_id] = historial

    historial.append({"role": "user", "content": mensaje_usuario})

    intencion = clasificar_intencion(mensaje_usuario)
    logger.info(f"[INTENCIÓN DETECTADA] {intencion} para: '{mensaje_usuario}'")

    # =========================================================
    # INTENCIÓN DE PAGO / FINALIZAR PEDIDO ("ya termine mi pedido quiero pagar")
    # =========================================================
    if es_intencion_pago(mensaje_usuario):
        session_sandwich_state.pop(session_id, None)
        pedido_db = db.query(Pedido).filter(Pedido.session_id == session_id, Pedido.estado == "en_proceso").first()
        if pedido_db and len(pedido_db.detalles) > 0 and pedido_db.total > 0:
            total_fmt = f"{pedido_db.total:,}".replace(",", ".")
            respuesta_texto = (
                f"¡Excelente! Tu total es de ${total_fmt} CLP. "
                "Muchas gracias por comprar en Cliff, recuerda que nuestros envases son reciclables y ecológicos."
            )
            items = [
                ItemPedido(
                    id=d.id,
                    producto_id=d.producto_id,
                    nombre=d.producto.nombre if d.producto else "Producto",
                    categoria=d.producto.categoria if d.producto else "",
                    cantidad=d.cantidad,
                    precio_unitario=d.precio_unitario,
                    subtotal=d.subtotal,
                    descripcion_adicional=d.descripcion_adicional or "",
                )
                for d in pedido_db.detalles
            ]
            pedido_actual = PedidoActual(id=pedido_db.id, session_id=session_id, total=pedido_db.total, estado=pedido_db.estado, items=items)
            historial.append({"role": "assistant", "content": respuesta_texto})
            return ChatResponse(
                respuesta_texto=respuesta_texto,
                pedido_actual=pedido_actual,
                productos_ofrecidos=[],
                mostrar_pago=True,
            )
        else:
            respuesta_texto = "Aún no tienes productos agregados a tu pedido. Por favor dime qué te gustaría ordenar antes de proceder al pago."
            pedido_actual = PedidoActual(session_id=session_id, total=0, estado="en_proceso", items=[])
            historial.append({"role": "assistant", "content": respuesta_texto})
            return ChatResponse(
                respuesta_texto=respuesta_texto,
                pedido_actual=pedido_actual,
                productos_ofrecidos=[],
                mostrar_pago=False,
            )

    agregados_en_turno = []
    agotados_en_turno = []
    sandwich_custom_armado = None
    productos_ofrecidos_orden: List[Dict[str, Any]] = []
    respuesta_texto = ""

    # =========================================================
    # FLUJO ESPECIAL: SANDWICHES PERSONALIZADOS (PAN OBLIGATORIO -> INGREDIENTES)
    # =========================================================
    estado_sandwich = session_sandwich_state.get(session_id)
    quiere_sandwich = es_intencion_sandwich_custom(mensaje_usuario)
    base_detectada = identificar_base_en_texto(db, mensaje_usuario)
    ings_detectados = identificar_ingredientes_adicionales_en_texto(db, mensaje_usuario)

    bases_disp = db.query(Producto).filter(
        (Producto.tipo_personalizado == "base") | (Producto.categoria == "Panes"),
        Producto.stock_disponible > 0,
        getattr(Producto, "activo", 1) == 1
    ).all()
    ings_disp = db.query(Producto).filter(
        (Producto.tipo_personalizado == "ingrediente") | (Producto.categoria.in_(["Proteínas", "Agregados", "Salsas"]) & (Producto.tipo_personalizado != "base")),
        Producto.stock_disponible > 0,
        getattr(Producto, "activo", 1) == 1
    ).all()

    # Si no hay estado activo pero el usuario menciona ingredientes y tiene un sandwich en el pedido:
    # Reconectar automáticamente al sandwich existente
    if not estado_sandwich and ings_detectados:
        pedido_db_check = db.query(Pedido).filter(Pedido.session_id == session_id, Pedido.estado == "en_proceso").first()
        ultimo_sw = None
        if pedido_db_check:
            for d in reversed(pedido_db_check.detalles):
                if (d.producto and d.producto.nombre == "Sandwich Personalizado") or (d.descripcion_adicional and d.descripcion_adicional.startswith("🥖")):
                    ultimo_sw = d
                    break
        if ultimo_sw:
            estado_sandwich = {
                "paso": "armando_sandwich",
                "base_id": 0,
                "base_nombre": "tu sandwich",
                "ingredientes_acumulados": [],
                "detalle_id": ultimo_sw.id
            }
            session_sandwich_state[session_id] = estado_sandwich

    if estado_sandwich or quiere_sandwich or base_detectada:
        # CASO 1: Estábamos esperando que el cliente elija la base
        if estado_sandwich and estado_sandwich.get("paso") == "esperando_base":
            if base_detectada:
                pendientes = estado_sandwich.get("ingredientes_pendientes") or []
                nuevos_ings = [i.id for i in ings_detectados]
                todos_ings = list(dict.fromkeys(pendientes + nuevos_ings))

                if todos_ings:
                    # El cliente ya tenía ingredientes o los nombró junto con el pan: ¡Armar y mantener abierto!
                    res_custom = tool_armar_sandwich_personalizado(db, session_id, [base_detectada.id] + todos_ings)
                    if res_custom.get("exito"):
                        session_sandwich_state[session_id] = {
                            "paso": "armando_sandwich",
                            "base_id": base_detectada.id,
                            "base_nombre": base_detectada.nombre,
                            "ingredientes_acumulados": todos_ings,
                            "detalle_id": res_custom.get("detalle_id")
                        }
                        desc = res_custom["descripcion"]
                        precio = res_custom["precio_sandwich"]
                        nombres_nuevos = [p.nombre for p in db.query(Producto).filter(Producto.id.in_(todos_ings)).all()]
                        respuesta_texto = (
                            f"¡Listo! Armé tu sandwich en {base_detectada.nombre} con {', '.join(nombres_nuevos)} ({desc}) por ${precio} CLP. "
                            "¿Deseas sumarle algún otro ingrediente (como palta, queso o salsas) o ya está listo?"
                        )
                        productos_ofrecidos_orden = [producto_a_ofrecido(p) for p in ings_disp]
                    elif res_custom.get("motivo") == "AGOTADO":
                        agotados_en_turno.append({"nombre": res_custom.get("ingrediente_agotado"), "sustitutos": res_custom.get("sustitutos_disponibles", [])})
                    else:
                        respuesta_texto = res_custom.get("mensaje", "")
                else:
                    # Solo eligió el pan: avanzar a base elegida
                    session_sandwich_state[session_id] = {
                        "paso": "base_elegida",
                        "base_id": base_detectada.id,
                        "base_nombre": base_detectada.nombre,
                        "ingredientes_acumulados": []
                    }
                    respuesta_texto = (
                        f"¡Excelente! Has seleccionado {base_detectada.nombre}. "
                        "Ahora dime por voz qué ingredientes deseas agregarle: por ejemplo carne mechada, pollo, palta, queso o salsas."
                    )
                    productos_ofrecidos_orden = [producto_a_ofrecido(p) for p in ings_disp]
            else:
                # No dijo pan: ¿mencionó ingredientes?
                if ings_detectados:
                    pendientes = estado_sandwich.get("ingredientes_pendientes") or []
                    pendientes.extend([i.id for i in ings_detectados])
                    estado_sandwich["ingredientes_pendientes"] = list(dict.fromkeys(pendientes))
                    prods_n = [p.nombre for p in db.query(Producto).filter(Producto.id.in_(estado_sandwich["ingredientes_pendientes"])).all()]
                    respuesta_texto = (
                        f"Anoté {', '.join(prods_n)}. Para continuar es obligatorio elegir el pan: "
                        "1) Pan Frica Artesanal, 2) Pan Ciabatta Rústico o 3) Pan de Molde Integral. "
                        "¿Cuál prefieres? Puedes decir 'el primero' o el nombre del pan."
                    )
                else:
                    respuesta_texto = (
                        "Para armar tu sandwich personalizado es obligatorio elegir primero el pan (base). "
                        "Opciones disponibles: 1) Pan Frica Artesanal, 2) Pan Ciabatta Rústico o 3) Pan de Molde Integral. "
                        "¿Cuál prefieres? Puedes decir 'el primero' o el nombre del pan."
                    )
                productos_ofrecidos_orden = [producto_a_ofrecido(p) for p in bases_disp]

        # CASO 2: El cliente ya tiene la base elegida y estamos recibiendo ingredientes
        elif estado_sandwich and estado_sandwich.get("paso") == "base_elegida":
            # Si el usuario pide cancelar
            if any(w in mensaje_usuario.lower() for w in ["cancelar", "anular", "no quiero", "mejor no"]):
                session_sandwich_state.pop(session_id, None)
                respuesta_texto = "Listo, cancelé el armado de sandwich. ¿Qué te gustaría pedir?"

            # Si el usuario quiere cambiar de pan
            elif base_detectada and base_detectada.id != estado_sandwich.get("base_id") and not ings_detectados:
                estado_sandwich["base_id"] = base_detectada.id
                estado_sandwich["base_nombre"] = base_detectada.nombre
                respuesta_texto = f"Cambié tu pan a {base_detectada.nombre}. ¿Qué ingredientes deseas agregarle?"
                productos_ofrecidos_orden = [producto_a_ofrecido(p) for p in ings_disp]

            # Si el usuario repite o confirma el mismo pan que ya tiene
            elif base_detectada and base_detectada.id == estado_sandwich.get("base_id") and not ings_detectados:
                respuesta_texto = (
                    f"Tu base {estado_sandwich['base_nombre']} ya está confirmada. "
                    "Por favor dime por voz los ingredientes que deseas ponerle: por ejemplo carne mechada, pollo, palta, queso o salsas."
                )
                productos_ofrecidos_orden = [producto_a_ofrecido(p) for p in ings_disp]

            # Si el usuario mencionó ingredientes: ¡Armar e iniciar modo incremental!
            elif ings_detectados:
                acumulados = estado_sandwich.get("ingredientes_acumulados") or []
                todos_ings = list(dict.fromkeys(acumulados + [i.id for i in ings_detectados]))
                res_custom = tool_armar_sandwich_personalizado(db, session_id, [estado_sandwich["base_id"]] + todos_ings)
                if res_custom.get("exito"):
                    session_sandwich_state[session_id] = {
                        "paso": "armando_sandwich",
                        "base_id": estado_sandwich["base_id"],
                        "base_nombre": estado_sandwich["base_nombre"],
                        "ingredientes_acumulados": todos_ings,
                        "detalle_id": res_custom.get("detalle_id")
                    }
                    nombres_nuevos = [i.nombre for i in ings_detectados]
                    desc = res_custom["descripcion"]
                    precio = res_custom["precio_sandwich"]
                    respuesta_texto = (
                        f"¡Agregué {', '.join(nombres_nuevos)} a tu sandwich en {estado_sandwich['base_nombre']}! "
                        f"(Lleva: {desc}) por ${precio} CLP. "
                        "¿Deseas sumarle algún otro ingrediente (como palta, queso o salsas) o ya está listo?"
                    )
                    productos_ofrecidos_orden = [producto_a_ofrecido(p) for p in ings_disp]
                elif res_custom.get("motivo") == "AGOTADO":
                    agotados_en_turno.append({"nombre": res_custom.get("ingrediente_agotado"), "sustitutos": res_custom.get("sustitutos_disponibles", [])})
                else:
                    respuesta_texto = res_custom.get("mensaje", "")

            # Si dice que solo quiere el pan
            elif any(w in mensaje_usuario.lower() for w in ["solo el pan", "sin nada", "así no más", "asi no mas", "listo", "nada más", "nada mas"]):
                res_custom = tool_armar_sandwich_personalizado(db, session_id, [estado_sandwich["base_id"]])
                session_sandwich_state.pop(session_id, None)
                if res_custom.get("exito"):
                    sandwich_custom_armado = res_custom
            else:
                respuesta_texto = (
                    f"Ya tienes seleccionado tu pan {estado_sandwich['base_nombre']}. "
                    "Dime por voz qué ingredientes (carnes, agregados o salsas) deseas incluir en tu sandwich."
                )
                productos_ofrecidos_orden = [producto_a_ofrecido(p) for p in ings_disp]

        # CASO 2.5: El sandwich ya está en el pedido y el cliente añade más ingredientes o finaliza
        elif estado_sandwich and estado_sandwich.get("paso") == "armando_sandwich":
            # Si el cliente indica que está listo
            if any(w in mensaje_usuario.lower() for w in ["listo", "nada más", "nada mas", "así no más", "asi no mas", "así está bien", "asi esta bien", "eso sería", "eso seria", "eso es todo", "terminar", "no", "no gracias", "ok listo", "así está", "asi esta"]):
                session_sandwich_state.pop(session_id, None)
                respuesta_texto = "¡Perfecto! Tu sandwich personalizado quedó listo en el pedido. ¿Deseas pedir algo más para tomar o acompañar?"
                extras = db.query(Producto).filter(Producto.categoria.in_(["Acompañamientos", "Bebidas"]), Producto.stock_disponible > 0, getattr(Producto, "activo", 1) == 1).all()
                productos_ofrecidos_orden = [producto_a_ofrecido(p) for p in extras[:6]]

            # Si añade más ingredientes
            elif ings_detectados:
                nuevos_ids = [i.id for i in ings_detectados]
                res_add = tool_agregar_ingrediente_a_sandwich_existente(db, session_id, nuevos_ids, detalle_id=estado_sandwich.get("detalle_id"))
                if res_add.get("exito"):
                    acum = estado_sandwich.get("ingredientes_acumulados") or []
                    estado_sandwich["ingredientes_acumulados"] = list(dict.fromkeys(acum + nuevos_ids))
                    nombres_nuevos = [i.nombre for i in ings_detectados]
                    desc = res_add["descripcion"]
                    precio = res_add["precio_sandwich"]
                    respuesta_texto = (
                        f"¡Sumé {', '.join(nombres_nuevos)} a tu sandwich! "
                        f"Ahora lleva: {desc} (${precio} CLP). "
                        "¿Deseas agregar algún otro ingrediente o ya está listo?"
                    )
                    productos_ofrecidos_orden = [producto_a_ofrecido(p) for p in ings_disp]
                elif res_add.get("motivo") == "AGOTADO":
                    agotados_en_turno.append({"nombre": res_add.get("ingrediente_agotado"), "sustitutos": res_add.get("sustitutos_disponibles", [])})
                else:
                    respuesta_texto = res_add.get("mensaje", "")

            # Si pide cancelar
            elif any(w in mensaje_usuario.lower() for w in ["cancelar", "anular"]):
                session_sandwich_state.pop(session_id, None)
                respuesta_texto = "Listo, cancelé la edición de tu sandwich. ¿Qué más deseas pedir?"

            # Si pide un producto regular (ej: bebidas, papas)
            else:
                session_sandwich_state.pop(session_id, None)

        # CASO 3: Nueva solicitud de armar sandwich
        else:
            if base_detectada:
                if ings_detectados:
                    # El usuario dio el pan Y los ingredientes en su primer mensaje por voz: ¡Armar directo y permitir seguir sumando!
                    res_custom = tool_armar_sandwich_personalizado(db, session_id, [base_detectada.id] + [i.id for i in ings_detectados])
                    if res_custom.get("exito"):
                        session_sandwich_state[session_id] = {
                            "paso": "armando_sandwich",
                            "base_id": base_detectada.id,
                            "base_nombre": base_detectada.nombre,
                            "ingredientes_acumulados": [i.id for i in ings_detectados],
                            "detalle_id": res_custom.get("detalle_id")
                        }
                        nombres_nuevos = [i.nombre for i in ings_detectados]
                        desc = res_custom["descripcion"]
                        precio = res_custom["precio_sandwich"]
                        respuesta_texto = (
                            f"¡Listo! Armé tu sandwich en {base_detectada.nombre} con {', '.join(nombres_nuevos)} ({desc}) por ${precio} CLP. "
                            "¿Deseas sumarle algún otro ingrediente (como palta, queso o salsas) o ya está listo?"
                        )
                        productos_ofrecidos_orden = [producto_a_ofrecido(p) for p in ings_disp]
                    elif res_custom.get("motivo") == "AGOTADO":
                        agotados_en_turno.append({"nombre": res_custom.get("ingrediente_agotado"), "sustitutos": res_custom.get("sustitutos_disponibles", [])})
                    else:
                        respuesta_texto = res_custom.get("mensaje", "")
                else:
                    # El usuario indicó solo el pan al inicio
                    session_sandwich_state[session_id] = {
                        "paso": "base_elegida",
                        "base_id": base_detectada.id,
                        "base_nombre": base_detectada.nombre,
                        "ingredientes_acumulados": []
                    }
                    respuesta_texto = (
                        f"¡Excelente elección con el {base_detectada.nombre}! "
                        "Ahora dime por voz qué ingredientes deseas agregarle (por ejemplo: carne mechada, pollo, palta, queso o salsas)."
                    )
                    productos_ofrecidos_orden = [producto_a_ofrecido(p) for p in ings_disp]
            else:
                # No especificó pan: Registrar estado y exigir pan primero
                session_sandwich_state[session_id] = {
                    "paso": "esperando_base",
                    "ingredientes_pendientes": [i.id for i in ings_detectados]
                }
                if ings_detectados:
                    nombres_i = [i.nombre for i in ings_detectados]
                    respuesta_texto = (
                        f"Para tu sandwich con {', '.join(nombres_i)}, primero debes elegir el pan (base obligatoria): "
                        "1) Pan Frica Artesanal, 2) Pan Ciabatta Rústico o 3) Pan de Molde Integral. "
                        "¿Cuál prefieres? Puedes decir 'el primero' o el nombre del pan."
                    )
                else:
                    respuesta_texto = (
                        "¡Con gusto te ayudo a armar tu sandwich! Primero debemos elegir la base (pan obligatorio): "
                        "1) Pan Frica Artesanal, 2) Pan Ciabatta Rústico o 3) Pan de Molde Integral. "
                        "¿Cuál prefieres? Dímelo por voz o elígelo en pantalla."
                    )
                productos_ofrecidos_orden = [producto_a_ofrecido(p) for p in bases_disp]

    # =========================================================
    # FLUJO 1: PREGUNTAS Y CONSULTAS (SI NO FUE MANEJADO POR SANDWICH)
    # =========================================================
    elif intencion == "CONSULTA":
        respuesta_texto, productos_ofrecidos_raw = generar_respuesta_consulta(mensaje_usuario, db)
        historial.append({"role": "assistant", "content": respuesta_texto})

        pedido_db = db.query(Pedido).filter(Pedido.session_id == session_id, Pedido.estado == "en_proceso").first()
        if pedido_db:
            pedido_actual = PedidoActual(
                id=pedido_db.id,
                session_id=pedido_db.session_id,
                total=pedido_db.total,
                estado=pedido_db.estado,
                items=[
                    ItemPedido(
                        id=d.id,
                        producto_id=d.producto_id,
                        nombre=d.producto.nombre if d.producto else "Producto",
                        categoria=d.producto.categoria if d.producto else "",
                        cantidad=d.cantidad,
                        precio_unitario=d.precio_unitario,
                        subtotal=d.subtotal,
                        descripcion_adicional=d.descripcion_adicional or "",
                    )
                    for d in pedido_db.detalles
                ],
            )
        else:
            pedido_actual = PedidoActual(session_id=session_id, total=0, estado="en_proceso", items=[])

        return ChatResponse(
            respuesta_texto=respuesta_texto,
            pedido_actual=pedido_actual,
            productos_ofrecidos=[ProductoOfrecido(**p) for p in productos_ofrecidos_raw],
        )

    # =========================================================
    # FLUJO 2: ORDENAR PRODUCTOS REGULARES EXPLÍCITAMENTE
    # =========================================================
    else:
        cant = extraer_cantidad_desde_texto(mensaje_usuario)
        res_add = tool_agregar_al_pedido(db, session_id, 0, cant, texto_contexto=mensaje_usuario)
        if res_add.get("exito"):
            agregados_en_turno.append(res_add)
        elif res_add.get("motivo") == "AGOTADO":
            agotados_en_turno.append({
                "nombre": res_add.get("producto"),
                "sustitutos": res_add.get("sustitutos_disponibles", []),
            })
        else:
            mensajes_llm = [{"role": "system", "content": SYSTEM_PROMPT}] + historial
            try:
                llm_response = openai_client.chat.completions.create(
                    model=MODEL_NAME,
                    messages=mensajes_llm,
                    tools=TOOLS,
                    tool_choice="auto",
                    temperature=0.05,
                )
                msg_choice = llm_response.choices[0].message
                tool_calls = getattr(msg_choice, "tool_calls", None)
                if not tool_calls:
                    fallback_call = extraer_tool_call_desde_texto(msg_choice.content)
                    if fallback_call:
                        fn_name, fn_args = fallback_call
                        tool_calls = [SyntheticToolCall("call_synth_1", fn_name, fn_args)]

                if tool_calls:
                    for tc in tool_calls:
                        if tc.function.name == "agregar_al_pedido":
                            args = json.loads(getattr(tc.function, "arguments", "{}"))
                            r_tool = tool_agregar_al_pedido(db, session_id, args.get("producto_id"), args.get("cantidad", 1), texto_contexto=mensaje_usuario)
                            if r_tool.get("exito"):
                                agregados_en_turno.append(r_tool)
                            elif r_tool.get("motivo") == "AGOTADO":
                                agotados_en_turno.append({"nombre": r_tool.get("producto"), "sustitutos": r_tool.get("sustitutos_disponibles", [])})
            except Exception as e:
                logger.error(f"Error en llamada fallback LLM: {e}")

    # Síntesis de respuesta para orden
    if agotados_en_turno:
        agotado = agotados_en_turno[0]
        nombre_agotado = agotado.get("nombre") or "Ese producto"
        sustitutos = agotado.get("sustitutos") or []
        sust_texto = f", pero te ofrezco {sustitutos[0]}" if sustitutos else ""
        respuesta_texto = f"Disculpa, no nos queda {nombre_agotado} en stock{sust_texto}. ¿Te gustaría agregarlo?"

        # Poner sustituto en pantalla
        if sustitutos:
            sust_prod = db.query(Producto).filter(Producto.nombre.ilike(f"%{sustitutos[0].split('(')[0].strip()}%")).first()
            if sust_prod:
                productos_ofrecidos_orden.append(producto_a_ofrecido(sust_prod, "Sustituto disponible recomendado"))

    elif sandwich_custom_armado and not respuesta_texto:
        desc = sandwich_custom_armado["descripcion"]
        precio = sandwich_custom_armado["precio_sandwich"]
        tot = sandwich_custom_armado["total_pedido"]
        respuesta_texto = f"¡Listo! Armé tu sandwich personalizado ({desc}) por ${precio} CLP. Total pedido: ${tot} CLP."

    elif agregados_en_turno:
        ultimo = agregados_en_turno[-1]
        prod_nom = ultimo["producto"]
        cant = ultimo["cantidad"]
        tot = ultimo["total_pedido"]
        respuesta_texto = f"¡Listo! Agregué {cant}x {prod_nom} a tu pedido. El total acumulado es ${tot} CLP."

    elif not respuesta_texto:
        respuesta_texto = "Listo, he procesado tu solicitud."

    historial.append({"role": "assistant", "content": respuesta_texto})

    # Obtener estado actual del pedido en SQLite
    pedido_db = db.query(Pedido).filter(Pedido.session_id == session_id, Pedido.estado == "en_proceso").first()
    if pedido_db:
        pedido_actual = PedidoActual(
            id=pedido_db.id,
            session_id=pedido_db.session_id,
            total=pedido_db.total,
            estado=pedido_db.estado,
            items=[
                ItemPedido(
                    id=d.id,
                    producto_id=d.producto_id,
                    nombre=d.producto.nombre if d.producto else "Producto",
                    categoria=d.producto.categoria if d.producto else "",
                    cantidad=d.cantidad,
                    precio_unitario=d.precio_unitario,
                    subtotal=d.subtotal,
                    descripcion_adicional=d.descripcion_adicional or "",
                )
                for d in pedido_db.detalles
            ],
        )
    else:
        pedido_actual = PedidoActual(session_id=session_id, total=0, estado="en_proceso", items=[])

    return ChatResponse(
        respuesta_texto=respuesta_texto,
        pedido_actual=pedido_actual,
        productos_ofrecidos=[ProductoOfrecido(**p) for p in productos_ofrecidos_orden],
    )


# ==========================================
# ENDPOINTS ADICIONALES DEL KIOSCO
# ==========================================
@app.get("/api/pedido/{session_id}", response_model=PedidoActual)
async def obtener_pedido(session_id: str, db: Session = Depends(get_db)):
    """Devuelve el estado del pedido actual de la sesión."""
    pedido = db.query(Pedido).filter(Pedido.session_id == session_id, Pedido.estado == "en_proceso").first()
    if not pedido:
        return PedidoActual(session_id=session_id, total=0, estado="en_proceso", items=[])

    return PedidoActual(
        id=pedido.id,
        session_id=pedido.session_id,
        total=pedido.total,
        estado=pedido.estado,
        items=[
            ItemPedido(
                id=d.id,
                producto_id=d.producto_id,
                nombre=d.producto.nombre if d.producto else "Producto",
                categoria=d.producto.categoria if d.producto else "",
                cantidad=d.cantidad,
                precio_unitario=d.precio_unitario,
                subtotal=d.subtotal,
                descripcion_adicional=d.descripcion_adicional or "",
            )
            for d in pedido.detalles
        ],
    )


@app.get("/api/productos")
async def listar_productos(db: Session = Depends(get_db)):
    """Lista todos los productos del inventario con su stock actual e imagen en SQLite."""
    productos = db.query(Producto).all()
    return [p.to_dict() for p in productos]


@app.get("/api/ingredientes")
async def listar_ingredientes(db: Session = Depends(get_db)):
    """Devuelve los ingredientes disponibles para armar sandwiches, con identificación de bases e ingredientes."""
    categorias = ["Panes", "Proteínas", "Agregados", "Salsas"]
    productos = db.query(Producto).filter(
        (Producto.tipo_personalizado.in_(["base", "ingrediente"])) | (Producto.categoria.in_(categorias)),
        getattr(Producto, "activo", 1) == 1
    ).all()

    bases = [p.to_dict() for p in productos if getattr(p, "tipo_personalizado", "ninguno") == "base" or p.categoria == "Panes"]
    ingredientes = [
        p.to_dict() for p in productos 
        if getattr(p, "tipo_personalizado", "ninguno") == "ingrediente" or (p.categoria in ["Proteínas", "Agregados", "Salsas"] and getattr(p, "tipo_personalizado", "ninguno") != "base")
    ]

    agrupados = {cat: [] for cat in categorias}
    for p in productos:
        if p.categoria in agrupados:
            agrupados[p.categoria].append(p.to_dict())

    return {
        "bases": bases,
        "ingredientes": ingredientes,
        **agrupados
    }


@app.post("/api/pedido/{session_id}/armar-sandwich")
async def api_armar_sandwich(session_id: str, req: ArmarSandwichDirectoRequest, db: Session = Depends(get_db)):
    """Arma un sandwich personalizado en el pedido exigiendo primero la base y luego los ingredientes."""
    base = db.query(Producto).filter(Producto.id == req.base_id).first()
    if not base or (getattr(base, "tipo_personalizado", "ninguno") != "base" and base.categoria != "Panes"):
        raise HTTPException(status_code=400, detail="Es obligatorio seleccionar una base (pan) válida para el sandwich.")
    
    if base.stock_disponible <= 0:
        raise HTTPException(status_code=400, detail=f"El pan seleccionado '{base.nombre}' está agotado.")

    todos_ids = [base.id] + (req.ingredientes_ids or [])
    res = tool_armar_sandwich_personalizado(db, session_id, todos_ids, texto_contexto="")
    if not res.get("exito"):
        raise HTTPException(status_code=400, detail=res.get("mensaje", "No se pudo armar el sandwich."))
    
    # Limpiar estado conversacional si estaba activo
    session_sandwich_state.pop(session_id, None)

    return await obtener_pedido(session_id, db)


@app.post("/api/nuevo-pedido/{session_id}")
async def reiniciar_pedido(session_id: str, db: Session = Depends(get_db)):
    """Cierra la orden actual e inicia una sesión limpia."""
    if session_id in session_histories:
        session_histories[session_id] = []
    if session_id in session_sandwich_state:
        session_sandwich_state.pop(session_id, None)

    pedido = db.query(Pedido).filter(Pedido.session_id == session_id, Pedido.estado == "en_proceso").first()
    if pedido:
        pedido.estado = "completado"
        db.commit()

    return {"mensaje": "Pedido finalizado y sesión reiniciada.", "session_id": session_id}


class ItemDirectoRequest(BaseModel):
    producto_id: int
    cantidad: int = 1


class ItemAjusteRequest(BaseModel):
    detalle_id: int
    delta: int  # 1: sumar 1, -1: restar 1, 0: eliminar


@app.post("/api/pedido/{session_id}/agregar-directo")
async def agregar_item_directo(session_id: str, req: ItemDirectoRequest, db: Session = Depends(get_db)):
    """Agrega un producto directamente al pedido de la sesión sin pasar por LLM."""
    res = tool_agregar_al_pedido(db, session_id, req.producto_id, req.cantidad, texto_contexto="")
    if not res.get("exito"):
        raise HTTPException(status_code=400, detail=res.get("mensaje", "No se pudo agregar el producto."))
    return await obtener_pedido(session_id, db)


@app.post("/api/pedido/{session_id}/ajustar-item")
async def ajustar_item_pedido(session_id: str, req: ItemAjusteRequest, db: Session = Depends(get_db)):
    """Aumenta (+1), reduce (-1) o elimina (0) un ítem del pedido, sincronizando el stock en SQLite."""
    pedido = db.query(Pedido).filter(Pedido.session_id == session_id, Pedido.estado == "en_proceso").first()
    if not pedido:
        raise HTTPException(status_code=404, detail="Pedido no encontrado.")

    detalle = db.query(DetallePedido).filter(DetallePedido.id == req.detalle_id, DetallePedido.pedido_id == pedido.id).first()
    if not detalle:
        raise HTTPException(status_code=404, detail="Detalle no encontrado en el pedido.")

    producto = detalle.producto
    if req.delta > 0:
        if producto:
            if producto.stock_disponible < 1:
                raise HTTPException(status_code=400, detail=f"No hay más stock disponible de {producto.nombre}.")
            producto.stock_disponible -= 1
        detalle.cantidad += 1
        detalle.subtotal = detalle.cantidad * detalle.precio_unitario
    elif req.delta < 0:
        if detalle.cantidad > 1:
            detalle.cantidad -= 1
            detalle.subtotal = detalle.cantidad * detalle.precio_unitario
            if producto:
                producto.stock_disponible += 1
        else:
            if producto:
                producto.stock_disponible += detalle.cantidad
            db.delete(detalle)
    else:
        if producto:
            producto.stock_disponible += detalle.cantidad
        db.delete(detalle)

    db.flush()
    pedido.total = sum(d.subtotal for d in pedido.detalles)
    db.commit()
    return await obtener_pedido(session_id, db)



# ==========================================
# ENDPOINTS DEL PANEL DE ADMINISTRACIÓN
# ==========================================
@app.get("/api/admin/metricas")
async def admin_metricas(db: Session = Depends(get_db)):
    """Devuelve estadísticas en tiempo real del inventario SQLite para el dashboard."""
    productos = db.query(Producto).all()
    total_prods = len(productos)
    total_stock = sum(p.stock_disponible for p in productos)
    agotados = sum(1 for p in productos if p.stock_disponible <= 0)
    stock_bajo = sum(1 for p in productos if 0 < p.stock_disponible <= 3)
    desactivados = sum(1 for p in productos if getattr(p, "activo", 1) == 0)
    categorias = sorted(list(set(p.categoria for p in productos if p.categoria)))
    
    valor_inventario = sum(p.precio * p.stock_disponible for p in productos)

    return {
        "total_productos": total_prods,
        "total_stock": total_stock,
        "productos_agotados": agotados,
        "productos_stock_bajo": stock_bajo,
        "productos_desactivados": desactivados,
        "categorias": categorias,
        "valor_inventario": valor_inventario,
    }


@app.post("/api/admin/productos")
async def crear_producto(data: ProductoCreate, db: Session = Depends(get_db)):
    """Crea un nuevo producto en la base de datos SQLite."""
    nombre_limpio = data.nombre.strip()
    categoria_limpia = data.categoria.strip()

    if not nombre_limpio:
        raise HTTPException(status_code=400, detail="El nombre del producto es obligatorio.")
    if not categoria_limpia:
        raise HTTPException(status_code=400, detail="La categoría del producto es obligatoria.")

    # Verificar si ya existe un producto con el mismo nombre
    existe = db.query(Producto).filter(Producto.nombre.ilike(nombre_limpio)).first()
    if existe:
        raise HTTPException(status_code=400, detail=f"Ya existe un producto registrado con el nombre '{nombre_limpio}'.")

    nuevo = Producto(
        nombre=nombre_limpio,
        categoria=categoria_limpia,
        precio=max(0, data.precio),
        stock_disponible=max(0, data.stock_disponible),
        imagen_url=data.imagen_url.strip() if data.imagen_url else None,
        activo=1 if data.activo is not False else 0,
        tipo_personalizado=data.tipo_personalizado.strip() if data.tipo_personalizado else "ninguno",
        es_vegetariano=1 if data.es_vegetariano else 0,
        es_vegano=1 if data.es_vegano else 0,
    )
    db.add(nuevo)
    db.commit()
    db.refresh(nuevo)
    logger.info(f"[ADMIN] Creado nuevo producto ID {nuevo.id}: {nuevo.nombre} (Tipo: {nuevo.tipo_personalizado}, Veg: {nuevo.es_vegetariano}, Vegan: {nuevo.es_vegano})")
    return nuevo.to_dict()


@app.put("/api/admin/productos/{producto_id}")
async def actualizar_producto(producto_id: int, data: ProductoUpdate, db: Session = Depends(get_db)):
    """Modifica los atributos de un producto existente (nombre, categoría, precio, stock, imagen, activo, tipo_personalizado, dietas)."""
    p = db.query(Producto).filter(Producto.id == producto_id).first()
    if not p:
        raise HTTPException(status_code=404, detail="Producto no encontrado en el inventario.")

    if data.nombre is not None:
        p.nombre = data.nombre.strip()
    if data.categoria is not None:
        p.categoria = data.categoria.strip()
    if data.precio is not None:
        p.precio = max(0, data.precio)
    if data.stock_disponible is not None:
        p.stock_disponible = max(0, data.stock_disponible)
    if data.imagen_url is not None:
        p.imagen_url = data.imagen_url.strip() if data.imagen_url else None
    if data.activo is not None:
        p.activo = 1 if data.activo else 0
    if data.tipo_personalizado is not None:
        p.tipo_personalizado = data.tipo_personalizado.strip()
    if data.es_vegetariano is not None:
        p.es_vegetariano = 1 if data.es_vegetariano else 0
    if data.es_vegano is not None:
        p.es_vegano = 1 if data.es_vegano else 0

    db.commit()
    db.refresh(p)
    logger.info(f"[ADMIN] Producto ID {p.id} actualizado exitosamente: {p.nombre} (Tipo: {p.tipo_personalizado}, Veg: {p.es_vegetariano}, Vegan: {p.es_vegano})")
    return p.to_dict()


@app.patch("/api/admin/productos/{producto_id}/estado")
async def cambiar_estado_producto(producto_id: int, data: Optional[EstadoUpdate] = None, db: Session = Depends(get_db)):
    """Activa o desactiva un producto de la carta en la base de datos SQLite."""
    p = db.query(Producto).filter(Producto.id == producto_id).first()
    if not p:
        raise HTTPException(status_code=404, detail="Producto no encontrado.")

    if data is not None and data.activo is not None:
        p.activo = 1 if data.activo else 0
    else:
        # Alternar (toggle) si no se especifica explícitamente
        p.activo = 0 if getattr(p, "activo", 1) == 1 else 1

    db.commit()
    db.refresh(p)
    nuevo_estado = "ACTIVO" if p.activo == 1 else "DESACTIVADO"
    logger.info(f"[ADMIN] Estado cambiado para producto ID {p.id} ({p.nombre}): {nuevo_estado}")
    return {"id": p.id, "nombre": p.nombre, "activo": bool(p.activo)}


@app.patch("/api/admin/productos/{producto_id}/stock")
async def actualizar_stock_producto(producto_id: int, data: StockUpdate, db: Session = Depends(get_db)):
    """Ajuste rápido de unidades de stock para el producto."""
    p = db.query(Producto).filter(Producto.id == producto_id).first()
    if not p:
        raise HTTPException(status_code=404, detail="Producto no encontrado.")

    p.stock_disponible = max(0, data.stock_disponible)
    db.commit()
    logger.info(f"[ADMIN] Stock actualizado para '{p.nombre}': {p.stock_disponible} unidades.")
    return {"id": p.id, "nombre": p.nombre, "stock_disponible": p.stock_disponible}


@app.patch("/api/admin/productos/{producto_id}/precio")
async def actualizar_precio_producto(producto_id: int, data: PrecioUpdate, db: Session = Depends(get_db)):
    """Ajuste rápido del precio unitario para el producto."""
    p = db.query(Producto).filter(Producto.id == producto_id).first()
    if not p:
        raise HTTPException(status_code=404, detail="Producto no encontrado.")

    p.precio = max(0, data.precio)
    db.commit()
    logger.info(f"[ADMIN] Precio actualizado para '{p.nombre}': ${p.precio} CLP.")
    return {"id": p.id, "nombre": p.nombre, "precio": p.precio}


@app.delete("/api/admin/productos/{producto_id}")
async def eliminar_producto(producto_id: int, db: Session = Depends(get_db)):
    """Elimina un producto de la base de datos SQLite."""
    p = db.query(Producto).filter(Producto.id == producto_id).first()
    if not p:
        raise HTTPException(status_code=404, detail="Producto no encontrado.")

    # Si tiene referencias históricas en DetallePedido, limpiar o eliminar
    db.query(DetallePedido).filter(DetallePedido.producto_id == producto_id).delete(synchronize_session=False)
    db.delete(p)
    db.commit()
    logger.info(f"[ADMIN] Producto ID {producto_id} eliminado exitosamente.")
    return {"mensaje": f"Producto '{p.nombre}' eliminado correctamente.", "id": producto_id}


@app.post("/api/admin/upload-imagen")
async def subir_imagen_producto(file: UploadFile = File(...)):
    """
    Sube un archivo de imagen al servidor y lo guarda en /static/uploads/.
    Devuelve la URL accesible para asignarla al producto.
    """
    allowed_exts = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".svg"}
    original_name = file.filename or "imagen.jpg"
    ext = os.path.splitext(original_name)[1].lower()

    if ext not in allowed_exts:
        raise HTTPException(status_code=400, detail="Formato no admitido. Se aceptan archivos JPG, PNG, WEBP o SVG.")

    # Generar nombre único seguro
    nombre_seguro = f"prod_{uuid.uuid4().hex[:12]}{ext}"
    ruta_destino = os.path.join(UPLOADS_DIR, nombre_seguro)

    try:
        with open(ruta_destino, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
    except Exception as e:
        logger.error(f"Error al guardar archivo subido: {e}")
        raise HTTPException(status_code=500, detail="Error interno al guardar la imagen en el servidor.")

    url_relativa = f"/static/uploads/{nombre_seguro}"
    logger.info(f"[ADMIN] Imagen subida y guardada: {url_relativa}")
    return {"url": url_relativa, "filename": nombre_seguro}


# ==========================================
# RUTAS DE INTERFACES WEB
# ==========================================
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/")
async def index():
    """Sirve la interfaz web del kiosco de autoservicio."""
    return FileResponse(os.path.join(STATIC_DIR, "index.html"))


@app.get("/admin")
async def admin_page():
    """Sirve la interfaz gráfica del panel de administración."""
    return FileResponse(os.path.join(STATIC_DIR, "admin.html"))


@app.get("/admin.html")
async def admin_page_html():
    """Ruta alternativa para acceder al panel de administración."""
    return FileResponse(os.path.join(STATIC_DIR, "admin.html"))


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)
