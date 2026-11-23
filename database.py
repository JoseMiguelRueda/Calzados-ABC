from datetime import datetime, date
from sqlalchemy import (
    create_engine, Column, Integer, String, Boolean, Date, DateTime,
    Float, ForeignKey, UniqueConstraint
)
from sqlalchemy.orm import declarative_base, sessionmaker, relationship, scoped_session

Base = declarative_base()


class Persona(Base):
    __tablename__ = "Persona"
    id = Column(Integer, primary_key=True)
    nombre = Column(String(120), nullable=False)
    nit = Column(String(30), nullable=False)
    telefono = Column(String(30), nullable=False)
    direccion = Column(String(200), nullable=False)

    usuario = relationship("Usuario", back_populates="persona", uselist=False, cascade="all, delete-orphan")
    cliente = relationship("Cliente", back_populates="persona", uselist=False, cascade="all, delete-orphan")


class Usuario(Base):
    __tablename__ = "Usuario"
    id = Column(Integer, ForeignKey("Persona.id"), primary_key=True)
    login = Column(String(100), unique=True, nullable=False)
    password = Column(String(255), nullable=False)
    rol = Column(String(40), nullable=False)
    activo = Column(Boolean, default=True, nullable=False)

    persona = relationship("Persona", back_populates="usuario")


class Cliente(Base):
    __tablename__ = "Cliente"
    id = Column(Integer, ForeignKey("Persona.id"), primary_key=True)
    razon_social = Column(String(150), nullable=False)
    estado_aval = Column(String(30), default="Pendiente", nullable=False)

    persona = relationship("Persona", back_populates="cliente")
    compromisos = relationship("Compromiso", back_populates="cliente", cascade="all, delete-orphan")
    pedidos = relationship("Pedido", back_populates="cliente", cascade="all, delete-orphan")


class Compromiso(Base):
    __tablename__ = "Compromiso"
    id = Column(Integer, primary_key=True)
    cliente_id = Column(Integer, ForeignKey("Cliente.id"), nullable=False)
    codigo_documento = Column(String(60), nullable=False)
    fecha_firma = Column(Date, nullable=False)
    archivo_pdf = Column(String(255), nullable=True)
    vigente = Column(Boolean, default=True, nullable=False)

    cliente = relationship("Cliente", back_populates="compromisos")


class Marca(Base):
    __tablename__ = "Marca"
    id = Column(Integer, primary_key=True)
    nombre = Column(String(80), unique=True, nullable=False)

    modelos = relationship("Modelo", back_populates="marca")
    calzados = relationship("Calzado", back_populates="marca")


class Modelo(Base):
    __tablename__ = "Modelo"
    id = Column(Integer, primary_key=True)
    marca_id = Column(Integer, ForeignKey("Marca.id"), nullable=False)
    nombre = Column(String(80), nullable=False)

    marca = relationship("Marca", back_populates="modelos")
    calzados = relationship("Calzado", back_populates="modelo")


class Color(Base):
    __tablename__ = "Color"
    id = Column(Integer, primary_key=True)
    color = Column(String(60), unique=True, nullable=False)

    calzados = relationship("Calzado", back_populates="color_obj")


class TipoCalzado(Base):
    __tablename__ = "TipoCalzado"
    id = Column(Integer, primary_key=True)
    descripcion = Column(String(80), unique=True, nullable=False)

    calzados = relationship("Calzado", back_populates="tipo")


class Talla(Base):
    __tablename__ = "Talla"
    id = Column(Integer, primary_key=True)
    eu = Column(String(15), nullable=False)
    usa = Column(String(15), default="")
    jp = Column(String(15), default="")
    br = Column(String(15), default="")
    cm = Column(String(15), default="")

    calzados = relationship("Calzado", back_populates="talla")


class Almacen(Base):
    __tablename__ = "Almacen"
    id = Column(Integer, primary_key=True)
    nombre = Column(String(100), unique=True, nullable=False)
    ubicacion = Column(String(180), default="")
    es_central = Column(Boolean, default=False, nullable=False)

    stocks = relationship("StockAlmacen", back_populates="almacen", cascade="all, delete-orphan")


class Calzado(Base):
    __tablename__ = "Calzado"
    id = Column(Integer, primary_key=True)
    codigo = Column(String(50), unique=True, nullable=False)
    marca_id = Column(Integer, ForeignKey("Marca.id"), nullable=False)
    modelo_id = Column(Integer, ForeignKey("Modelo.id"), nullable=False)
    color_id = Column(Integer, ForeignKey("Color.id"), nullable=False)
    tipo_calzado_id = Column(Integer, ForeignKey("TipoCalzado.id"), nullable=False)
    talla_id = Column(Integer, ForeignKey("Talla.id"), nullable=False)
    precio_mayorista = Column(Float, default=120.0, nullable=False)
    stock_disponible = Column(Integer, default=20, nullable=False)
    stock_reservado = Column(Integer, default=0, nullable=False)
    activo = Column(Boolean, default=True, nullable=False)

    __table_args__ = (
        UniqueConstraint("marca_id", "modelo_id", "color_id", "talla_id", name="uq_calzado_combinacion"),
    )

    marca = relationship("Marca", back_populates="calzados")
    modelo = relationship("Modelo", back_populates="calzados")
    color_obj = relationship("Color", back_populates="calzados")
    tipo = relationship("TipoCalzado", back_populates="calzados")
    talla = relationship("Talla", back_populates="calzados")
    detalles_pedido = relationship("DetallePedido", back_populates="calzado")
    stocks_almacen = relationship("StockAlmacen", back_populates="calzado", cascade="all, delete-orphan")
    importaciones = relationship("ImportacionFabrica", back_populates="calzado")


class StockAlmacen(Base):
    __tablename__ = "StockAlmacen"
    id = Column(Integer, primary_key=True)
    almacen_id = Column(Integer, ForeignKey("Almacen.id"), nullable=False)
    calzado_id = Column(Integer, ForeignKey("Calzado.id"), nullable=False)
    cantidad = Column(Integer, default=0, nullable=False)

    __table_args__ = (
        UniqueConstraint("almacen_id", "calzado_id", name="uq_almacen_calzado"),
    )

    almacen = relationship("Almacen", back_populates="stocks")
    calzado = relationship("Calzado", back_populates="stocks_almacen")


class Pedido(Base):
    __tablename__ = "Pedido"
    id = Column(Integer, primary_key=True)
    codigo_pedido = Column(String(40), unique=True, nullable=False)
    cliente_id = Column(Integer, ForeignKey("Cliente.id"), nullable=False)
    fecha_creacion = Column(DateTime, default=datetime.utcnow, nullable=False)
    estado = Column(String(30), default="Pendiente", nullable=False)
    total = Column(Float, default=0.0, nullable=False)
    fecha_estimada_entrega = Column(Date, nullable=True)
    observacion = Column(String(250), default="")

    cliente = relationship("Cliente", back_populates="pedidos")
    detalles = relationship("DetallePedido", back_populates="pedido", cascade="all, delete-orphan")


class DetallePedido(Base):
    __tablename__ = "DetallePedido"
    id = Column(Integer, primary_key=True)
    pedido_id = Column(Integer, ForeignKey("Pedido.id"), nullable=False)
    calzado_id = Column(Integer, ForeignKey("Calzado.id"), nullable=False)
    cantidad = Column(Integer, nullable=False)
    cantidad_reservada = Column(Integer, default=0, nullable=False)
    cantidad_faltante = Column(Integer, default=0, nullable=False)
    precio_unitario = Column(Float, nullable=False)
    subtotal = Column(Float, nullable=False)

    pedido = relationship("Pedido", back_populates="detalles")
    calzado = relationship("Calzado", back_populates="detalles_pedido")


class ImportacionFabrica(Base):
    __tablename__ = "ImportacionFabrica"
    id = Column(Integer, primary_key=True)
    codigo_lote = Column(String(50), unique=True, nullable=False)
    fabrica = Column(String(120), nullable=False)
    calzado_id = Column(Integer, ForeignKey("Calzado.id"), nullable=False)
    almacen_id = Column(Integer, ForeignKey("Almacen.id"), nullable=False)
    cantidad = Column(Integer, nullable=False)
    fecha_arribo = Column(Date, default=date.today, nullable=False)
    fecha_creacion = Column(DateTime, default=datetime.utcnow, nullable=False)

    calzado = relationship("Calzado", back_populates="importaciones")
    almacen = relationship("Almacen")


class TraspasoAlmacen(Base):
    __tablename__ = "TraspasoAlmacen"
    id = Column(Integer, primary_key=True)
    codigo_traspaso = Column(String(50), unique=True, nullable=False)
    almacen_origen_id = Column(Integer, ForeignKey("Almacen.id"), nullable=False)
    almacen_destino_id = Column(Integer, ForeignKey("Almacen.id"), nullable=False)
    calzado_id = Column(Integer, ForeignKey("Calzado.id"), nullable=False)
    cantidad = Column(Integer, nullable=False)
    fecha_traspaso = Column(DateTime, default=datetime.utcnow, nullable=False)

    almacen_origen = relationship("Almacen", foreign_keys=[almacen_origen_id])
    almacen_destino = relationship("Almacen", foreign_keys=[almacen_destino_id])
    calzado = relationship("Calzado")


def get_session(db_url="sqlite:///calzados_abc.db"):
    engine = create_engine(db_url, connect_args={"check_same_thread": False} if db_url.startswith("sqlite") else {})
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine)
    return scoped_session(session_factory)
