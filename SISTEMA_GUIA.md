# Guía de Arquitectura, Memoria del Sistema e Historial de Cambios (Voice Bistro)

> **PROPÓSITO DE ESTE ARCHIVO**:  
> Este documento contiene la arquitectura completa, el esquema de datos, el funcionamiento de la lógica de voz/IA y el historial detallado de todos los cambios implementados en el proyecto. Cualquier agente de IA (Antigravity u otro) debe leer este archivo para entender el estado actual del sistema y guiarse antes y durante cualquier modificación.

---

## 1. Visión General del Proyecto

**Voice Bistro** es un sistema de kiosco de autoservicio inteligente que opera de forma 100% local.
- **Frontend**: Single-Page Application (SPA) con HTML5, Vanilla CSS3 y Vanilla JavaScript moderno. Sin dependencias externas pesadas.
- **Backend**: FastAPI (Python 3.10+ / Python 3.14) con arquitectura asíncrona.
- **Base de Datos**: SQLite local (`pedidos.db`) gestionada con SQLAlchemy ORM.
- **Motor de Lenguaje (LLM)**: Ollama local ejecutando el modelo `llama3.2:1b` (o compatible) en GPU/VRAM.
- **Voz y Audio**: Web Speech API nativa (reconocimiento `webkitSpeechRecognition` y síntesis `speechSynthesis`).

---

## 2. Mapa de Archivos del Repositorio

| Archivo / Carpeta | Descripción y Rol |
| :--- | :--- |
| `main.py` | API principal FastAPI. Contiene endpoints REST, lifespan con migraciones SQLite en caliente, orquestación del chat con IA (`/api/chat-pedido`), tools de inventario y pedidos, y websocket/rutas de administración. |
| `models.py` | Modelos de base de datos SQLAlchemy (`Producto`, `Pedido`, `DetallePedido`), semillas de catálogo (`seed_data`), mapeo de imágenes por defecto (`IMAGENES_DEFAULT`) y dietas (`DIET_INFO_DEFAULT`). |
| `database.py` | Conexión SQLite con SQLAlchemy (`engine`, `SessionLocal`, `Base`, generador `get_db`). |
| `static/index.html` | Estructura del Kiosco de Autoservicio con 3 vistas (`view-welcome`, `view-ai-kiosk`, `view-traditional-menu`), armador modal de sandwiches (`modal-custom-sandwich`), drawer del carrito (`cart-drawer`) y modal de pago. |
| `static/app.js` | Lógica de cliente del kiosco: reconocimiento y síntesis de voz, máquina de estados de UI, renderizado de productos y recomendaciones, armador interactivo paso a paso, drawer del carrito y conexión con la API. |
| `static/style.css` | Sistema de diseño: paleta oscura moderna (obsidiana, cian, esmeralda, ámbar), layout de pantalla completa, cuadro de recomendaciones estático con scroll interno, modales y micro-animaciones. |
| `static/admin.html` | Interfaz web del Panel Administrativo (`/admin`): métricas de inventario, tabla y grid de productos, filtros por stock, categoría, rol y dieta, y modal de creación/edición. |
| `static/admin.js` | Lógica de cliente del panel administrativo: consumo de endpoints de `/api/admin/*`, filtrado reactivo, sincronización mutua de checkboxes vegetariano/vegano, subida de imágenes y edición en tiempo real. |
| `iniciar.sh` / `iniciar.bat` | Scripts de arranque para Linux/macOS y Windows con chequeo de Python, Ollama y creación de entorno virtual. |
| `pedidos.db` | Base de datos SQLite activa. |
| `scratch/test_custom_sandwich_flow.py` | Suite automatizada de pruebas unitarias y de integración para validar el flujo conversacional por voz y atributos dietéticos. |

---

## 3. Esquema de Base de Datos SQLite (`pedidos.db`)

### Tabla: `productos`
- `id` (INTEGER, Primary Key, Autoincremental)
- `nombre` (VARCHAR(150), Unique, Not Null)
- `categoria` (VARCHAR(100), Not Null): *Panes, Proteínas, Agregados, Salsas, Comidas, Acompañamientos, Bebidas, Cafetería, Postres, Sandwiches Custom*.
- `precio` (INTEGER, Not Null): Precio en pesos chilenos (CLP).
- `stock_disponible` (INTEGER, Not Null, Default 10)
- `imagen_url` (VARCHAR(500), Nullable): URL externa o ruta local de imagen (`/uploads/...`).
- `activo` (INTEGER, Not Null, Default 1): 1 = disponible en la carta; 0 = desactivado del menú.
- `tipo_personalizado` (VARCHAR(30), Not Null, Default 'ninguno'):
  - `'base'`: Panes obligatorios que inician el armado de un sandwich.
  - `'ingrediente'`: Proteínas, agregados, quesos y salsas que complementan el sandwich.
  - `'ninguno'`: Productos regulares de la carta.
- `es_vegetariano` (INTEGER, Not Null, Default 0): 1 = Apto vegetariano; 0 = No vegetariano.
- `es_vegano` (INTEGER, Not Null, Default 0): 1 = Apto vegano; 0 = No vegano (Nota: todo producto vegano es también vegetariano).

### Tabla: `pedidos`
- `id` (INTEGER, Primary Key, Autoincremental)
- `session_id` (VARCHAR(100), Unique, Not Null): Identificador único de la sesión del cliente/kiosco.
- `estado` (VARCHAR(50), Default 'en_proceso'): *en_proceso, pagado, cancelado*.
- `fecha` (DATETIME, Default UTC now)
- `total` (INTEGER, Default 0): Suma total en CLP.

### Tabla: `detalles_pedido`
- `id` (INTEGER, Primary Key, Autoincremental)
- `pedido_id` (INTEGER, Foreign Key `pedidos.id`)
- `producto_id` (INTEGER, Foreign Key `productos.id`)
- `cantidad` (INTEGER, Not Null, Default 1)
- `precio_unitario` (INTEGER, Not Null)
- `subtotal` (INTEGER, Not Null)
- `descripcion_adicional` (VARCHAR(500), Nullable): Detalle de ingredientes para sandwiches personalizados (ej: `🥖 Pan Frica Artesanal + Carne Mechada Casera + Palta Hass Molida`).

---

## 4. Lógica Conversacional y Máquina de Estados de IA

### Flujo de Sandwiches Personalizados
1. **Regla de Oro**: La base de pan (`tipo_personalizado == 'base'`) es **estrictamente obligatoria** antes de elegir cualquier ingrediente.
2. **Estados en `session_sandwich_state[session_id]`**:
   - `esperando_base`: El usuario indicó intención de armar un sandwich o preguntó por ingredientes. La IA ofrece únicamente las bases de pan en pantalla y solicita verbalmente elegir el pan.
   - `base_elegida`: El usuario seleccionó su base (por nombre o por ordinal como *"el primero"*, *"la segunda opción"*). La IA confirma el pan y despliega todos los ingredientes disponibles.
   - `armando_sandwich`: Contiene `base_id`, `base_nombre`, `detalle_id` (del ítem en `DetallePedido`), y `ingredientes_acumulados`. Permite adición incremental por voz en múltiples turnos.
3. **Adición Incremental Multi-Turno**:
   - Cuando el cliente dice *"Ponle carne mechada"*, se crea o actualiza el sandwich y el estado pasa a `armando_sandwich`.
   - Cuando en turnos posteriores dice *"y también palta"* o *"agrégale queso cheddar"*, la tool `tool_agregar_ingrediente_a_sandwich_existente` anexa los ingredientes **DENTRO** del mismo sandwich, recalculando el precio sin crear ítems huérfanos fuera del sandwich.
   - Cuando el cliente dice *"listo"*, *"nada más"* o *"eso es todo"*, el sandwich se finaliza y se limpia el estado para continuar con bebidas u otros ítems.
4. **Intercepción de Ingredientes Sueltos**:
   - Si un usuario pide directamente un ingrediente (ej: *"quiero palta"* o *"agrega mayonesa"*) y ya tiene un sandwich personalizado en su carrito, el sistema lo integra automáticamente en ese sandwich. Si no tiene sandwich, le recuerda amablemente elegir primero la base de pan.

---

## 5. Diseño de Interfaz y Reglas de Maquetación de la Pantalla IA

### Cuadro Central Estático con Scroll Interno
- **Problema previo resuelto**: Al desplegar recomendaciones (por ejemplo, 15 ingredientes o múltiples opciones vegetarianas), el contenedor crecía verticalmente empujando la barra de acciones inferior fuera de la pantalla, perdiéndose de vista el botón de hablar (`#btn-mic`).
- **Regla de Maquetación**:
  1. `.ai-central-box` (`#ai-central-box`) tiene dimensiones estáticas y no debe expandirse hacia abajo ni desplazar la barra inferior.
  2. `.ai-bottom-actions-bar` permanece siempre anclada y 100% visible con el botón de micrófono (`#btn-mic`) en su posición fija.
  3. `.ai-offered-section` y `#ai-cards-grid` (el cuadro interno de recomendaciones) maneja `overflow-y: auto`, permitiendo al usuario subir y bajar con scroll suave cuando se muestran muchos productos, sin alterar el tamaño del cuadro externo.

---

## 6. Historial Cronológico de Cambios y Mejoras

### Versión 1.0 - Creación del Sistema Base
- Servidor FastAPI con endpoints REST y panel SQLite.
- Integración de Ollama (`llama3.2:1b`) con function calling / tools.
- Kiosco táctil con reconocimiento de voz en tiempo real y drawer de carrito.

### Versión 1.1 - Clasificación de Roles para Sandwiches Personalizados
- Agregada columna `tipo_personalizado` (`base`, `ingrediente`, `ninguno`).
- Actualizado catálogo inicial en `models.py` con panes e ingredientes clasificados.
- Agregado filtro de rol e insignias en el Panel de Administración (`/admin`).
- Creado modal interactivo de dos pasos: Paso 1 Pan obligatorio (Paso 2 bloqueado con overlay hasta elegir pan) y Paso 2 Selección múltiple de ingredientes con total en vivo.

### Versión 1.2 - Eliminación de Bucle en Selección de Pan por Voz
- Solucionado el problema donde decir el pan por voz volvía a preguntar por el pan.
- Implementada detección robusta de ordinales (*el primero*, *el 2*, *la tercera opción*).
- Prevención de duplicados por subcadenas (ej. no confundir *queso cheddar* con *queso gauda*).
- Manejo de confirmación sin bucle si el usuario repite el pan.

### Versión 1.3 - Armado Incremental por Voz y Clasificación Vegetariana / Vegana
- **Armado Incremental Multi-Turno**: Al hablar en oraciones separadas (*"carne mechada"* -> *"y palta"* -> *"y queso"*), los ingredientes se suman dentro del mismo sandwich (`tool_agregar_ingrediente_a_sandwich_existente`), evitando productos huérfanos en el carrito.
- **Atributos Dietéticos**: Columnas `es_vegetariano` y `es_vegano` en `productos`.
- **Filtro Dietético en Admin**: Selector en `/admin` para filtrar por *Toda la Dieta*, *Solo Vegetarianos*, *Solo Veganos* o *Con Carne*.
- **Checkboxes en Modal de Producto**: Opciones independientes con sincronización mutua (marcar vegano marca automáticamente vegetariano).
- **Insignias Dietéticas**: Etiquetas `🌱 Veg` y `🌿 Vegano` en catálogo, tarjetas y tabla.
- **Consultas Dietéticas por Voz**: Respuestas automáticas ante preguntas sobre opciones vegetarianas o veganas.

### Versión 1.4 - Cuadro de Recomendaciones Estático con Scroll Interno
- Contenedor `.ai-central-box` configurado para mantener altura estática y evitar crecimiento desmedido.
- `.ai-cards-grid` y `.ai-offered-section` con `overflow-y: auto` y scrollbar estilizado para navegar múltiples productos internamente.
- Botón de hablar (`#btn-mic`) en `.ai-bottom-actions-bar` visible en todo momento sin desplazamientos indeseados.

### Versión 1.5 - Rediseño de Identidad CLIFF, Pantalla de Pago y Mensaje Ecológico
- **Identidad Visual CLIFF**:
  - Reemplazo de paleta por la identidad oficial: Azul marino profundo (`#1b324f`), lienzo cálido arena/beige (`#ece8e1`), tarjetas blancas limpias (`#ffffff`) con bordes cálidos (`#dfdad0`), acento verde WhatsApp (`#25D366`) y esmeralda (`#16a34a`).
  - Barra superior con logotipo CLIFF, botón de compartir y botón directo de WhatsApp.
  - Menú tradicional con Sidebar de categorías lateral izquierdo, título `— Sandwiches`, y tarjetas de producto horizontales con detalle de gramaje de ingredientes, precios duales (*Normal $X* / *+ Papa $X*) y botón `+ Agregar`.
  - Botón flotante inferior derecho con lupa para alternar al Autoservicio IA.
- **Flujo de Pago por Voz**:
  - Función `es_intencion_pago(texto: str) -> bool` en `main.py` para detectar expresiones como *"ya termine mi pedido quiero pagar"*, *"quiero pagar"*, *"la cuenta"*, etc.
  - La IA calcula el total y responde de forma vocal y textual con la frase exacta:
    *"¡Excelente! Tu total es de ${total_fmt} CLP. Muchas gracias por comprar en Cliff, recuerda que nuestros envases son reciclables y ecológicos."*
  - Se activa `mostrar_pago: True` en `ChatResponse`, abriendo de inmediato la Pantalla de Pago (`#modal-pago`).
- **Pantalla de Pago y Cierre Ecológico**:
  - Desglose detallado de productos con cantidades, ingredientes y subtotales.
  - Selección de métodos de pago (Tarjeta POS Totem, QR/Transferencia, Efectivo en Caja).
  - Banner verde ecológico destacado con el compromiso reciclable.
  - Al presionar *Pagar y Confirmar Orden*, el bot vocaliza nuevamente la frase de agradecimiento ecológico y despliega el modal de confirmación final.
- **Verificación Completa**:
### Versión 1.6 - Limpieza de Cabecera IA, Eliminación de Chips y Corrección de Tarjetas Recomendadas
- **Eliminación de Barra Superior y Chips en Pantalla IA**:
  - Eliminado el encabezado `.ai-box-header` (*"✨ Aquí dentro va lo que ofrece la IA Listo para escuchar..."*).
  - Eliminado el contenedor `.suggestions-container` (*"Prueba diciendo o pulsando:..."*).
  - Mayor espacio vertical útil dentro de `.ai-central-box` para mostrar los productos ofrecidos sin comprimir la interfaz.
- **Corrección de Tarjetas de Recomendación de la IA**:
  - **Nombre del Producto Visible y Destacado**: Se reposicionó el título del producto (`prod.nombre`) como el encabezado primario superior en tipografía gruesa y legible en azul marino profundo CLIFF (`var(--cliff-navy)`).
  - **Eliminación de Confusión de Categoría**: La categoría ya no reemplaza ni precede al nombre del producto; se muestra únicamente como una discreta insignia secundaria (`.card-cat-badge`) junto a las insignias dietéticas (`🌿 Vegano`, `🌱 Veg`) y de stock.
  - **Descripciones Enriquecidas Limpias**: Se eliminó el texto redundante que duplicaba la categoría y el precio (`Acompañamientos • $2.200 CLP`), mostrando en su lugar la descripción de ingredientes reales de `DESCRIPCIONES_CLIFF`.
### Versión 1.7 - Diseño Responsivo Auto-Ajustable y Nivelación de Botones Inferiores
- **Nivelación Exacta de Botones de Acción**:
  - Se calibraron `.big-mic-wrapper` y `.big-cart-button` a una altura idéntica en cada resolución (`96px` en desktop, `82px` en pantallas compactas, `80px` en tablets y `72px` en móviles).
  - El visualizador de ondas `#sound-wave` se posicionó de manera absoluta sobre el micrófono, eliminando el desplazamiento vertical asimétrico.
  - Los contenedores `.mic-action-container` y `.cart-action-container` tienen altura idéntica (`126px`), logrando que el botón de micrófono y el botón del carrito queden **a la misma altura exacta**, y sus textos descriptivos alineados sobre la misma línea horizontal.
- **Responsividad y Auto-Ajuste de la Pantalla IA**:
  - Eliminados los límites rígidos de altura (`max-height: 390px` en `.ai-offered-section` y `min-height: 480px` en `.ai-central-box`), permitiendo que el cuadro y las tarjetas se adapten naturalmente a la altura de la pantalla sin dejar espacios vacíos.
  - La barra de entrada de texto se ancla limpiamente al pie del cuadro (`margin-top: auto`).
  - Media queries responsivas añadidas para pantallas de escritorio amplias, laptops, tablets (768px) y dispositivos móviles (480px).

### Versión 1.8 - Botón de Micrófono Circular Perfecto, Expansión Total de Recomendaciones y Desactivación de Entrada de Texto
- **Corrección Geométrica del Botón de Micrófono**:
  - Solucionado el problema por el cual el botón del micrófono se mostraba como un óvalo vertical ("huevo") debido a que `#sound-wave` era un elemento flex hermano dentro de `.big-mic-wrapper`, reduciendo el ancho del botón a ~50px.
  - `#sound-wave` se extrajo al contenedor padre `.mic-action-container` y se posicionó de manera absoluta centrada en la parte superior (`top: -30px; left: 50%`) con `opacity: 0` cuando está en reposo (completamente invisible hasta que se inicia la grabación).
  - Se fijó `.big-mic-wrapper` y `.big-mic-button` con reglas estrictas de aspecto 1:1 (`aspect-ratio: 1 / 1; min-width: 96px; max-width: 96px; min-height: 96px; max-height: 96px; border-radius: 50%; box-sizing: border-box;`), asegurando un círculo perfecto tanto en escritorio como en todas las media queries responsivas.
  - Los anillos decorativos `.mic-ring` permanecen con `opacity: 0` en reposo para evitar bordes flotantes extraños, mostrándose solo durante la grabación activa.
- **Cuadro de Recomendaciones Ocupa Todo el Espacio Sobrante**:
  - Se configuró `.ai-offered-section` y `.ai-cards-grid` con `flex: 1; min-height: 0; height: 100%; width: 100%; max-height: none;`.
  - El cuadro de recomendaciones ahora se expande para abarcar todo el espacio vertical disponible dentro de `.ai-central-box` sin dejar huecos vacíos en blanco, conservando el scroll interno suave cuando se ofrecen múltiples productos.
- **Desactivación de la Opción de Escribir (Fácilmente Reactivable a Futuro)**:
  - Se ocultó y deshabilitó el formulario de entrada escrita `#chat-form` (`display: none !important;` tanto en línea como en `style.css`, con atributos `disabled` en el input y botón de envío).
  - El manejador de eventos en JavaScript se conserva intacto, de modo que en el futuro se puede reactivar inmediatamente solo cambiando `display: none` por `display: flex` y quitando los atributos `disabled`.

---

### Versión 1.9 - Soporte para Docker, Easypanel y Despliegues en Contenedores
- **Creación de Dockerfile**:
  - Imagen base ligera `python:3.11-slim`.
  - Instalación limpia de dependencias desde `requirements.txt`.
  - Healthcheck integrado con curl contra el puerto 8000.
  - Creación automática del directorio persistente `/app/static/uploads`.
- **Creación de .dockerignore**:
  - Exclusión de `venv/`, `__pycache__/`, `.git/` y artefactos temporales para optimizar el peso de la imagen de Docker.
- **Creación de docker-compose.yml**:
  - Definición de servicios `web` y `ollama` con volúmenes persistentes para la base de datos (`/app/pedidos.db`), fotos (`/app/static/uploads`) y modelos de IA (`/root/.ollama`).
- **Flexibilidad de Variables de Entorno en Backend**:
  - `main.py` ahora acepta tanto `OLLAMA_HOST` (estándar de Docker/Easypanel) como `OLLAMA_BASE_URL`, añadiendo automáticamente `/v1` si es necesario.
  - `database.py` ahora lee `DATABASE_URL` para permitir configurar la ruta del archivo SQLite montado en volumen persistente.

---

## 7. Guía de Ejecución y Pruebas para Agentes

1. **Iniciar Servidor Local**:
   ```bash
   ./venv/bin/uvicorn main:app --host 0.0.0.0 --port 8000
   ```
2. **Ejecutar Suite de Pruebas Automatizadas**:
   ```bash
   ./venv/bin/python scratch/test_custom_sandwich_flow.py
   ```
3. **Acceso Web**:
   - Kiosco: `http://localhost:8000/`
   - Panel Administrativo: `http://localhost:8000/admin`

