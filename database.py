from datetime import date
from sqlalchemy import create_engine, Column, Integer, String, Boolean, Date, ForeignKey, UniqueConstraint
from sqlalchemy.orm import declarative_base, relationship, sessionmaker

Base = declarative_base()

class Persona(Base):
    __tablename__ = 'persona'
    id = Column(Integer, primary_key=True, autoincrement=True)
    nombre = Column(String(120), nullable=False)
    nit = Column(String(30))
    telefono = Column(String(30))
    direccion = Column(String(200))

    usuario = relationship("Usuario", back_populates="persona", uselist=False, cascade="all, delete-orphan")
    cliente = relationship("Cliente", back_populates="persona", uselist=False, cascade="all, delete-orphan")


class Usuario(Base):
    __tablename__ = 'usuario'
    id = Column(Integer, ForeignKey('persona.id', ondelete='CASCADE'), primary_key=True)
    login = Column(String(60), unique=True, nullable=False)
    password = Column(String(255), nullable=False)
    rol = Column(String(50), nullable=False)
    activo = Column(Boolean, default=True, nullable=False)

    persona = relationship("Persona", back_populates="usuario")


class Cliente(Base):
    __tablename__ = 'cliente'
    id = Column(Integer, ForeignKey('persona.id', ondelete='CASCADE'), primary_key=True)
    razon_social = Column(String(150), nullable=False)
    estado_aval = Column(String(30), default='Pendiente', nullable=False)

    persona = relationship("Persona", back_populates="cliente")
    compromisos = relationship("Compromiso", back_populates="cliente", cascade="all, delete-orphan")


class Compromiso(Base):
    __tablename__ = 'compromiso'
    id = Column(Integer, primary_key=True, autoincrement=True)
    cliente_id = Column(Integer, ForeignKey('cliente.id', ondelete='CASCADE'), nullable=False)
    codigo_documento = Column(String(60), unique=True, nullable=False)
    fecha_firma = Column(Date, nullable=False, default=date.today)
    archivo_pdf = Column(String(255))
    vigente = Column(Boolean, default=True, nullable=False)

    cliente = relationship("Cliente", back_populates="compromisos")


class Marca(Base):
    __tablename__ = 'marca'
    id = Column(Integer, primary_key=True, autoincrement=True)
    nombre = Column(String(80), unique=True, nullable=False)

    modelos = relationship("Modelo", back_populates="marca")
    calzados = relationship("Calzado", back_populates="marca")


class Modelo(Base):
    __tablename__ = 'modelo'
    id = Column(Integer, primary_key=True, autoincrement=True)
    marca_id = Column(Integer, ForeignKey('marca.id'), nullable=False)
    nombre = Column(String(100), nullable=False)

    marca = relationship("Marca", back_populates="modelos")
    calzados = relationship("Calzado", back_populates="modelo")

    __table_args__ = (
        UniqueConstraint('marca_id', 'nombre', name='uq_modelo_marca_nombre'),
    )


class Color(Base):
    __tablename__ = 'color'
    id = Column(Integer, primary_key=True, autoincrement=True)
    color = Column(String(60), unique=True, nullable=False)

    calzados = relationship("Calzado", back_populates="color_obj")


class TipoCalzado(Base):
    __tablename__ = 'tipo_calzado'
    id = Column(Integer, primary_key=True, autoincrement=True)
    descripcion = Column(String(80), unique=True, nullable=False)

    calzados = relationship("Calzado", back_populates="tipo")


class Talla(Base):
    __tablename__ = 'talla'
    id = Column(Integer, primary_key=True, autoincrement=True)
    eu = Column(String(15))
    usa = Column(String(15))
    jp = Column(String(15))
    br = Column(String(15))
    cm = Column(String(15))

    calzados = relationship("Calzado", back_populates="talla")


class Calzado(Base):
    __tablename__ = 'calzado'
    id = Column(Integer, primary_key=True, autoincrement=True)
    codigo = Column(String(60), unique=True, nullable=False)
    marca_id = Column(Integer, ForeignKey('marca.id'), nullable=False)
    modelo_id = Column(Integer, ForeignKey('modelo.id'), nullable=False)
    color_id = Column(Integer, ForeignKey('color.id'), nullable=False)
    tipo_calzado_id = Column(Integer, ForeignKey('tipo_calzado.id'), nullable=False)
    talla_id = Column(Integer, ForeignKey('talla.id'), nullable=False)
    activo = Column(Boolean, default=True, nullable=False)

    marca = relationship("Marca", back_populates="calzados")
    modelo = relationship("Modelo", back_populates="calzados")
    color_obj = relationship("Color", back_populates="calzados")
    tipo = relationship("TipoCalzado", back_populates="calzados")
    talla = relationship("Talla", back_populates="calzados")

    __table_args__ = (
        UniqueConstraint('marca_id', 'modelo_id', 'color_id', 'talla_id', name='uk_calzado_combinacion'),
    )


def get_session(db_url="sqlite:///calzados_abc.db"):
    engine = create_engine(db_url, connect_args={"check_same_thread": False} if "sqlite" in db_url else {})
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    return Session()