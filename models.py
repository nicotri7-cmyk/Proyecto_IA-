"""
models.py
Definición de modelos de base de datos SQLAlchemy y función de semillero de datos (seed_data).
Incluye soporte para productos regulares e ingredientes para sandwiches personalizados con control de stock.
"""

from datetime import datetime
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey
from sqlalchemy.orm import relationship, Session
from database import Base


class Producto(Base):
    __tablename__ = "productos"

    id = Column(Integer, primary_key=True, index=True)
    nombre = Column(String(120), nullable=False)
    categoria = Column(String(60), nullable=False, index=True)
    precio = Column(Integer, nullable=False)
    stock_disponible = Column(Integer, nullable=False, default=0)
    imagen_url = Column(String(500), nullable=True)
    activo = Column(Integer, nullable=False, default=1)
    tipo_personalizado = Column(String(30), nullable=False, default="ninguno", index=True)
    es_vegetariano = Column(Integer, nullable=False, default=0)
    es_vegano = Column(Integer, nullable=False, default=0)

    # Relación inversa con detalles de pedido
    detalles = relationship("DetallePedido", back_populates="producto")

    def to_dict(self):
        return {
            "id": self.id,
            "nombre": self.nombre,
            "categoria": self.categoria,
            "precio": self.precio,
            "stock_disponible": self.stock_disponible,
            "imagen_url": self.imagen_url or "",
            "activo": bool(self.activo) if self.activo is not None else True,
            "tipo_personalizado": self.tipo_personalizado or "ninguno",
            "es_vegetariano": bool(self.es_vegetariano) if self.es_vegetariano is not None else False,
            "es_vegano": bool(self.es_vegano) if self.es_vegano is not None else False,
        }


class Pedido(Base):
    __tablename__ = "pedidos"

    id = Column(Integer, primary_key=True, index=True)
    session_id = Column(String(100), nullable=False, index=True)
    total = Column(Integer, nullable=False, default=0)
    estado = Column(String(50), nullable=False, default="en_proceso")
    creado_en = Column(DateTime, default=datetime.utcnow)

    # Relación con DetallePedido
    detalles = relationship("DetallePedido", back_populates="pedido", cascade="all, delete-orphan")

    def to_dict(self):
        return {
            "id": self.id,
            "session_id": self.session_id,
            "total": self.total,
            "estado": self.estado,
            "creado_en": self.creado_en.isoformat() if self.creado_en else None,
            "items": [detalle.to_dict() for detalle in self.detalles],
        }


class DetallePedido(Base):
    __tablename__ = "detalles_pedido"

    id = Column(Integer, primary_key=True, index=True)
    pedido_id = Column(Integer, ForeignKey("pedidos.id"), nullable=False)
    producto_id = Column(Integer, ForeignKey("productos.id"), nullable=False)
    cantidad = Column(Integer, nullable=False, default=1)
    precio_unitario = Column(Integer, nullable=False)
    subtotal = Column(Integer, nullable=False)
    descripcion_adicional = Column(String(250), nullable=True)

    # Relaciones
    pedido = relationship("Pedido", back_populates="detalles")
    producto = relationship("Producto", back_populates="detalles")

    def to_dict(self):
        return {
            "id": self.id,
            "pedido_id": self.pedido_id,
            "producto_id": self.producto_id,
            "nombre": self.producto.nombre if self.producto else "Producto",
            "categoria": self.producto.categoria if self.producto else "",
            "cantidad": self.cantidad,
            "precio_unitario": self.precio_unitario,
            "subtotal": self.subtotal,
            "descripcion_adicional": self.descripcion_adicional or "",
        }


IMAGENES_DEFAULT = {
    "Hamburguesa Clásica": "https://images.unsplash.com/photo-1568901346375-23c9450c58cd?w=500&auto=format&fit=crop&q=80",
    "Hamburguesa Doble Queso": "https://images.unsplash.com/photo-1586190848861-99aa4a171e90?w=500&auto=format&fit=crop&q=80",
    "Sandwich Mechada Palta": "https://images.unsplash.com/photo-1553909489-cd47e0907980?w=500&auto=format&fit=crop&q=80",
    "Empanada de Pino Horno": "https://images.unsplash.com/photo-1628840042765-356cda07504e?w=500&auto=format&fit=crop&q=80",
    "Papas Fritas Medianas": "https://images.unsplash.com/photo-1576107232684-1279f3908594?w=500&auto=format&fit=crop&q=80",
    "Papas Rústicas Cheddar": "https://images.unsplash.com/photo-1585109649139-366815a0d713?w=500&auto=format&fit=crop&q=80",
    "Aros de Cebolla Crujientes": "https://images.unsplash.com/photo-1639024471287-032f66e5f1d0?w=500&auto=format&fit=crop&q=80",
    "Bebida Cola 350ml": "https://images.unsplash.com/photo-1622483767028-3f66f32aef97?w=500&auto=format&fit=crop&q=80",
    "Bebida Limón 350ml": "https://images.unsplash.com/photo-1513558161293-cdaf765ed2fd?w=500&auto=format&fit=crop&q=80",
    "Jugo Natural Naranja": "https://images.unsplash.com/photo-1613478223719-2ab802602423?w=500&auto=format&fit=crop&q=80",
    "Jugo Natural Frutilla": "https://images.unsplash.com/photo-1553530666-ba11a7da3888?w=500&auto=format&fit=crop&q=80",
    "Café Americano 250ml": "https://images.unsplash.com/photo-1514432324607-a09d9b4aefdd?w=500&auto=format&fit=crop&q=80",
    "Brownie con Helado": "https://images.unsplash.com/photo-1606313564200-e75d5e30476c?w=500&auto=format&fit=crop&q=80",
    "Pan Frica Artesanal": "https://images.unsplash.com/photo-1509440159596-0249088772ff?w=500&auto=format&fit=crop&q=80",
    "Pan Ciabatta Rústico": "https://images.unsplash.com/photo-1586444248902-2f64eddc13df?w=500&auto=format&fit=crop&q=80",
    "Pan de Molde Integral": "https://images.unsplash.com/photo-1549931319-a545dcf3bc73?w=500&auto=format&fit=crop&q=80",
    "Carne Mechada Casera": "https://images.unsplash.com/photo-1544025162-d76694265947?w=500&auto=format&fit=crop&q=80",
    "Pollo a la Plancha": "https://images.unsplash.com/photo-1604908176997-125f25cc6f3d?w=500&auto=format&fit=crop&q=80",
    "Lomito de Cerdo": "https://images.unsplash.com/photo-1529692236671-f1f6cf9683ba?w=500&auto=format&fit=crop&q=80",
    "Hamburguesa de Res": "https://images.unsplash.com/photo-1550547660-d9450f859349?w=500&auto=format&fit=crop&q=80",
    "Palta Hass Molida": "https://images.unsplash.com/photo-1523049673857-eb18f1d7b578?w=500&auto=format&fit=crop&q=80",
    "Queso Gauda Fundido": "https://images.unsplash.com/photo-1486297678162-eb2a19b0a32d?w=500&auto=format&fit=crop&q=80",
    "Queso Cheddar Fundido": "https://images.unsplash.com/photo-1618160702438-9b02ab6515c9?w=500&auto=format&fit=crop&q=80",
    "Tomate en Rodajas": "https://images.unsplash.com/photo-1592924357228-91a4daadcfea?w=500&auto=format&fit=crop&q=80",
    "Cebolla Caramelizada": "https://images.unsplash.com/photo-1618512496248-a07fe83aa8cb?w=500&auto=format&fit=crop&q=80",
    "Champiñones Salteados": "https://images.unsplash.com/photo-1504674900247-0877df9cc836?w=500&auto=format&fit=crop&q=80",
    "Tocino Crocante": "https://images.unsplash.com/photo-1606851094655-b2593a9af63f?w=500&auto=format&fit=crop&q=80",
    "Mayonesa Casera": "https://images.unsplash.com/photo-1589301760014-d929f3979dbc?w=500&auto=format&fit=crop&q=80",
    "Salsa BBQ Ahumada": "https://images.unsplash.com/photo-1514944298352-f67451632742?w=500&auto=format&fit=crop&q=80",
    "Salsa Verde Cilantro": "https://images.unsplash.com/photo-1546069901-ba9599a7e63c?w=500&auto=format&fit=crop&q=80",
    "Sandwich Personalizado": "https://images.unsplash.com/photo-1528735602780-2552fd46c7af?w=500&auto=format&fit=crop&q=80",
    "Chacarero Mortal": "https://images.unsplash.com/photo-1553909489-cd47e0907980?w=500&auto=format&fit=crop&q=80",
    "Diputado Vulcano": "https://images.unsplash.com/photo-1568901346375-23c9450c58cd?w=500&auto=format&fit=crop&q=80",
    "Barros Luco": "https://images.unsplash.com/photo-1528735602780-2552fd46c7af?w=500&auto=format&fit=crop&q=80",
    "Asiento Italiano": "https://images.unsplash.com/photo-1509722747041-616f39b57569?w=500&auto=format&fit=crop&q=80",
    "Carne Magra": "https://images.unsplash.com/photo-1550547660-d9450f859349?w=500&auto=format&fit=crop&q=80",
}


DIET_INFO_DEFAULT = {
    # Sandwiches Tradicionales CLIFF
    "Chacarero Mortal": (False, False),
    "Diputado Vulcano": (False, False),
    "Barros Luco": (False, False),
    "Asiento Italiano": (False, False),
    "Carne Magra": (False, False),
    # Comidas preparadas
    "Hamburguesa Clásica": (False, False),
    "Hamburguesa Doble Queso": (False, False),
    "Sandwich Mechada Palta": (False, False),
    "Empanada de Pino Horno": (False, False),
    # Acompañamientos
    "Papas Fritas Medianas": (True, True),
    "Papas Rústicas Cheddar": (True, False),  # Queso cheddar fundido no vegano
    "Aros de Cebolla Crujientes": (True, True),
    # Bebidas
    "Bebida Cola 350ml": (True, True),
    "Bebida Limón 350ml": (True, True),
    "Jugo Natural Naranja": (True, True),
    "Jugo Natural Frutilla": (True, True),
    # Cafetería y Postres
    "Café Americano 250ml": (True, True),
    "Brownie con Helado": (True, False),  # Lácteos y huevo
    # Panes (Bases)
    "Pan Frica Artesanal": (True, True),
    "Pan Ciabatta Rústico": (True, True),
    "Pan de Molde Integral": (True, True),
    # Proteínas
    "Carne Mechada Casera": (False, False),
    "Pollo a la Plancha": (False, False),
    "Lomito de Cerdo": (False, False),
    "Hamburguesa de Res": (False, False),
    # Agregados
    "Palta Hass Molida": (True, True),
    "Queso Gauda Fundido": (True, False),
    "Queso Cheddar Fundido": (True, False),
    "Tomate en Rodajas": (True, True),
    "Cebolla Caramelizada": (True, True),
    "Champiñones Salteados": (True, True),
    "Tocino Crocante": (False, False),
    # Salsas
    "Mayonesa Casera": (True, False),  # Contiene huevo
    "Salsa BBQ Ahumada": (True, True),
    "Salsa Verde Cilantro": (True, True),
    # Sandwich customizado
    "Sandwich Personalizado": (True, True),
}


def seed_data(db: Session):
    """
    Inserta registros de prueba iniciales e ingredientes para sandwiches personalizados con imágenes ilustrativas.
    Garantiza que al menos 2 productos y 2 ingredientes tengan stock_disponible = 0 para pruebas de agotados.
    """
    # Si la tabla ya tiene datos pero no tiene ingredientes, agregarlos
    tiene_ingredientes = db.query(Producto).filter(Producto.categoria == "Panes").first() is not None
    conteo = db.query(Producto).count()

    if conteo == 0 or not tiene_ingredientes:
        productos_iniciales = [
            # Sandwiches Clásicos CLIFF
            Producto(nombre="Chacarero Mortal", categoria="Sandwiches", precio=7500, stock_disponible=25, imagen_url=IMAGENES_DEFAULT.get("Chacarero Mortal"), es_vegetariano=0, es_vegano=0),
            Producto(nombre="Diputado Vulcano", categoria="Sandwiches", precio=6700, stock_disponible=20, imagen_url=IMAGENES_DEFAULT.get("Diputado Vulcano"), es_vegetariano=0, es_vegano=0),
            Producto(nombre="Barros Luco", categoria="Sandwiches", precio=6500, stock_disponible=22, imagen_url=IMAGENES_DEFAULT.get("Barros Luco"), es_vegetariano=0, es_vegano=0),
            Producto(nombre="Asiento Italiano", categoria="Sandwiches", precio=7600, stock_disponible=18, imagen_url=IMAGENES_DEFAULT.get("Asiento Italiano"), es_vegetariano=0, es_vegano=0),
            Producto(nombre="Carne Magra", categoria="Sandwiches", precio=6300, stock_disponible=15, imagen_url=IMAGENES_DEFAULT.get("Carne Magra"), es_vegetariano=0, es_vegano=0),

            # Comidas preparadas
            Producto(nombre="Hamburguesa Clásica", categoria="Comidas", precio=4500, stock_disponible=15, imagen_url=IMAGENES_DEFAULT.get("Hamburguesa Clásica"), es_vegetariano=0, es_vegano=0),
            Producto(nombre="Hamburguesa Doble Queso", categoria="Comidas", precio=5800, stock_disponible=10, imagen_url=IMAGENES_DEFAULT.get("Hamburguesa Doble Queso"), es_vegetariano=0, es_vegano=0),
            Producto(nombre="Sandwich Mechada Palta", categoria="Comidas", precio=5200, stock_disponible=8, imagen_url=IMAGENES_DEFAULT.get("Sandwich Mechada Palta"), es_vegetariano=0, es_vegano=0),
            Producto(nombre="Empanada de Pino Horno", categoria="Comidas", precio=2200, stock_disponible=12, imagen_url=IMAGENES_DEFAULT.get("Empanada de Pino Horno"), es_vegetariano=0, es_vegano=0),
            
            # Acompañamientos
            Producto(nombre="Papas Fritas Medianas", categoria="Acompañamientos", precio=2200, stock_disponible=20, imagen_url=IMAGENES_DEFAULT.get("Papas Fritas Medianas"), es_vegetariano=1, es_vegano=1),
            Producto(nombre="Papas Rústicas Cheddar", categoria="Acompañamientos", precio=3000, stock_disponible=0, imagen_url=IMAGENES_DEFAULT.get("Papas Rústicas Cheddar"), es_vegetariano=1, es_vegano=0),  # AGOTADO
            Producto(nombre="Aros de Cebolla Crujientes", categoria="Acompañamientos", precio=2500, stock_disponible=14, imagen_url=IMAGENES_DEFAULT.get("Aros de Cebolla Crujientes"), es_vegetariano=1, es_vegano=1),
            
            # Bebidas
            Producto(nombre="Bebida Cola 350ml", categoria="Bebidas", precio=1500, stock_disponible=25, imagen_url=IMAGENES_DEFAULT.get("Bebida Cola 350ml"), es_vegetariano=1, es_vegano=1),
            Producto(nombre="Bebida Limón 350ml", categoria="Bebidas", precio=1500, stock_disponible=18, imagen_url=IMAGENES_DEFAULT.get("Bebida Limón 350ml"), es_vegetariano=1, es_vegano=1),
            Producto(nombre="Jugo Natural Naranja", categoria="Bebidas", precio=2000, stock_disponible=0, imagen_url=IMAGENES_DEFAULT.get("Jugo Natural Naranja"), es_vegetariano=1, es_vegano=1),  # AGOTADO
            Producto(nombre="Jugo Natural Frutilla", categoria="Bebidas", precio=2000, stock_disponible=9, imagen_url=IMAGENES_DEFAULT.get("Jugo Natural Frutilla"), es_vegetariano=1, es_vegano=1),
            
            # Cafetería y Postres
            Producto(nombre="Café Americano 250ml", categoria="Cafetería", precio=1800, stock_disponible=30, imagen_url=IMAGENES_DEFAULT.get("Café Americano 250ml"), es_vegetariano=1, es_vegano=1),
            Producto(nombre="Brownie con Helado", categoria="Postres", precio=2800, stock_disponible=7, imagen_url=IMAGENES_DEFAULT.get("Brownie con Helado"), es_vegetariano=1, es_vegano=0),

            # ========================================================
            # INGREDIENTES PARA SANDWICHES CUSTOMIZADOS
            # ========================================================
            # Panes (Bases obligatorias iniciales)
            Producto(nombre="Pan Frica Artesanal", categoria="Panes", precio=1000, stock_disponible=25, imagen_url=IMAGENES_DEFAULT.get("Pan Frica Artesanal"), tipo_personalizado="base", es_vegetariano=1, es_vegano=1),
            Producto(nombre="Pan Ciabatta Rústico", categoria="Panes", precio=1200, stock_disponible=20, imagen_url=IMAGENES_DEFAULT.get("Pan Ciabatta Rústico"), tipo_personalizado="base", es_vegetariano=1, es_vegano=1),
            Producto(nombre="Pan de Molde Integral", categoria="Panes", precio=900, stock_disponible=15, imagen_url=IMAGENES_DEFAULT.get("Pan de Molde Integral"), tipo_personalizado="base", es_vegetariano=1, es_vegano=1),

            # Proteínas / Carnes (Ingredientes)
            Producto(nombre="Carne Mechada Casera", categoria="Proteínas", precio=3200, stock_disponible=18, imagen_url=IMAGENES_DEFAULT.get("Carne Mechada Casera"), tipo_personalizado="ingrediente", es_vegetariano=0, es_vegano=0),
            Producto(nombre="Pollo a la Plancha", categoria="Proteínas", precio=2600, stock_disponible=15, imagen_url=IMAGENES_DEFAULT.get("Pollo a la Plancha"), tipo_personalizado="ingrediente", es_vegetariano=0, es_vegano=0),
            Producto(nombre="Lomito de Cerdo", categoria="Proteínas", precio=2800, stock_disponible=0, imagen_url=IMAGENES_DEFAULT.get("Lomito de Cerdo"), tipo_personalizado="ingrediente", es_vegetariano=0, es_vegano=0),  # AGOTADO
            Producto(nombre="Hamburguesa de Res", categoria="Proteínas", precio=2500, stock_disponible=16, imagen_url=IMAGENES_DEFAULT.get("Hamburguesa de Res"), tipo_personalizado="ingrediente", es_vegetariano=0, es_vegano=0),

            # Quesos y Agregados (Ingredientes)
            Producto(nombre="Palta Hass Molida", categoria="Agregados", precio=1500, stock_disponible=20, imagen_url=IMAGENES_DEFAULT.get("Palta Hass Molida"), tipo_personalizado="ingrediente", es_vegetariano=1, es_vegano=1),
            Producto(nombre="Queso Gauda Fundido", categoria="Agregados", precio=1000, stock_disponible=22, imagen_url=IMAGENES_DEFAULT.get("Queso Gauda Fundido"), tipo_personalizado="ingrediente", es_vegetariano=1, es_vegano=0),
            Producto(nombre="Queso Cheddar Fundido", categoria="Agregados", precio=1000, stock_disponible=18, imagen_url=IMAGENES_DEFAULT.get("Queso Cheddar Fundido"), tipo_personalizado="ingrediente", es_vegetariano=1, es_vegano=0),
            Producto(nombre="Tomate en Rodajas", categoria="Agregados", precio=600, stock_disponible=30, imagen_url=IMAGENES_DEFAULT.get("Tomate en Rodajas"), tipo_personalizado="ingrediente", es_vegetariano=1, es_vegano=1),
            Producto(nombre="Cebolla Caramelizada", categoria="Agregados", precio=800, stock_disponible=14, imagen_url=IMAGENES_DEFAULT.get("Cebolla Caramelizada"), tipo_personalizado="ingrediente", es_vegetariano=1, es_vegano=1),
            Producto(nombre="Champiñones Salteados", categoria="Agregados", precio=1000, stock_disponible=12, imagen_url=IMAGENES_DEFAULT.get("Champiñones Salteados"), tipo_personalizado="ingrediente", es_vegetariano=1, es_vegano=1),
            Producto(nombre="Tocino Crocante", categoria="Agregados", precio=1200, stock_disponible=0, imagen_url=IMAGENES_DEFAULT.get("Tocino Crocante"), tipo_personalizado="ingrediente", es_vegetariano=0, es_vegano=0),  # AGOTADO

            # Salsas (Ingredientes)
            Producto(nombre="Mayonesa Casera", categoria="Salsas", precio=300, stock_disponible=40, imagen_url=IMAGENES_DEFAULT.get("Mayonesa Casera"), tipo_personalizado="ingrediente", es_vegetariano=1, es_vegano=0),
            Producto(nombre="Salsa BBQ Ahumada", categoria="Salsas", precio=300, stock_disponible=30, imagen_url=IMAGENES_DEFAULT.get("Salsa BBQ Ahumada"), tipo_personalizado="ingrediente", es_vegetariano=1, es_vegano=1),
            Producto(nombre="Salsa Verde Cilantro", categoria="Salsas", precio=300, stock_disponible=25, imagen_url=IMAGENES_DEFAULT.get("Salsa Verde Cilantro"), tipo_personalizado="ingrediente", es_vegetariano=1, es_vegano=1),

            # Producto Base para Sandwich Custom
            Producto(nombre="Sandwich Personalizado", categoria="Sandwiches Custom", precio=0, stock_disponible=999, imagen_url=IMAGENES_DEFAULT.get("Sandwich Personalizado"), tipo_personalizado="ninguno", es_vegetariano=1, es_vegano=1),
        ]

        # Insertar solo los que no existan por nombre
        for prod in productos_iniciales:
            existe = db.query(Producto).filter(Producto.nombre == prod.nombre).first()
            if not existe:
                db.add(prod)
        db.commit()
        print(f"[SEED] Base de datos actualizada con catálogo e ingredientes de sandwiches.")

    # Actualizar imágenes, tipo_personalizado y dieta para productos existentes
    existentes = db.query(Producto).all()
    cambios = False
    for p in existentes:
        if not p.imagen_url and p.nombre in IMAGENES_DEFAULT:
            p.imagen_url = IMAGENES_DEFAULT[p.nombre]
            cambios = True
        
        # Sincronizar tipo_personalizado si no está establecido
        if not p.tipo_personalizado or p.tipo_personalizado == "ninguno":
            if p.categoria == "Panes":
                p.tipo_personalizado = "base"
                cambios = True
            elif p.categoria in ["Proteínas", "Agregados", "Salsas"]:
                p.tipo_personalizado = "ingrediente"
                cambios = True

        # Sincronizar dietas si coinciden con DIET_INFO_DEFAULT
        if p.nombre in DIET_INFO_DEFAULT:
            d_veg, d_vegan = DIET_INFO_DEFAULT[p.nombre]
            if p.es_vegetariano is None or p.es_vegetariano != (1 if d_veg else 0):
                p.es_vegetariano = 1 if d_veg else 0
                cambios = True
            if p.es_vegano is None or p.es_vegano != (1 if d_vegan else 0):
                p.es_vegano = 1 if d_vegan else 0
                cambios = True

    if cambios:
        db.commit()
        print(f"[SEED] Imágenes, roles y dietas (veg/vegano) sincronizados en productos existentes.")
