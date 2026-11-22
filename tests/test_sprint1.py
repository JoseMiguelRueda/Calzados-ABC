import pytest
from datetime import date
from werkzeug.security import generate_password_hash
from database import get_session, Persona, Usuario, Marca, Modelo, Color, TipoCalzado, Talla
from services import ControladorAcceso, ClienteService, CatalogoService, ReglaNegocioException


@pytest.fixture
def db_session():
    session = get_session("sqlite:///:memory:")
    tipo = TipoCalzado(descripcion="Sandalias")
    marca = Marca(nombre="Pampili")
    color = Color(color="Negro")
    talla = Talla(eu="27", usa="10", jp="16.5", br="25", cm="16.5")
    session.add_all([tipo, marca, color, talla])
    session.flush()

    modelo = Modelo(marca_id=marca.id, nombre="016")
    session.add(modelo)

    persona_activa = Persona(nombre="Juan Perez", nit="123456")
    session.add(persona_activa)
    session.flush()
    session.add(Usuario(
        id=persona_activa.id,
        login="juan@abc.com",
        password=generate_password_hash("clave123"),
        rol="Administrador",
        activo=True
    ))

    persona_inactiva = Persona(nombre="Carlos Inactivo", nit="999999")
    session.add(persona_inactiva)
    session.flush()
    session.add(Usuario(
        id=persona_inactiva.id,
        login="carlos@abc.com",
        password=generate_password_hash("clave123"),
        rol="Encargado de Pedidos",
        activo=False
    ))
    session.commit()
    return session


def test_cp01_login_exitoso(db_session):
    auth = ControladorAcceso(db_session)
    usuario = auth.autenticar("juan@abc.com", "clave123")
    assert usuario.login == "juan@abc.com"
    assert usuario.rol == "Administrador"


def test_cp02_login_invalido_y_suspendido(db_session):
    auth = ControladorAcceso(db_session)
    with pytest.raises(ReglaNegocioException) as exc:
        auth.autenticar("juan@abc.com", "incorrecta")
    assert "Credenciales inválidas" in str(exc.value)

    with pytest.raises(ReglaNegocioException) as exc_susp:
        auth.autenticar("carlos@abc.com", "clave123")
    assert "Cuenta suspendida" in str(exc_susp.value)


def test_cp03_registrar_cliente_con_aval_vigente(db_session):
    srv = ClienteService(db_session)
    cliente = srv.registrarClienteConAval(
        nombre="Maria Lopez", nit="456789", telefono="77711223",
        direccion="Feria Barrio Lindo", razon_social="Comercial Maria",
        codigo_documento="DOC-001", fecha_firma=date(2026, 11, 20),
        archivo_pdf="compromiso_maria.pdf", login="maria@tienda.com",
        password="pass123", aval_vigente=True
    )
    assert cliente.estado_aval == "Vigente"
    assert cliente.persona.usuario.login == "maria@tienda.com"


def test_cp04_bloqueo_cliente_sin_aval(db_session):
    srv = ClienteService(db_session)
    cliente = srv.registrarClienteConAval(
        nombre="Pedro SinAval", nit="111222", telefono="70000000",
        direccion="La Ramada", razon_social="Tienda Pedro",
        codigo_documento="DOC-002", fecha_firma=date(2026, 11, 20),
        archivo_pdf="", login="pedro@tienda.com",
        password="pass123", aval_vigente=False
    )
    with pytest.raises(ReglaNegocioException) as exc:
        srv.validarPermisoPedido(cliente.id)
    assert exc.value.codigo == "E1"


def test_cp05_registrar_calzado_valido(db_session):
    srv = CatalogoService(db_session)
    marca = db_session.query(Marca).first()
    modelo = db_session.query(Modelo).first()
    color = db_session.query(Color).first()
    tipo = db_session.query(TipoCalzado).first()
    talla = db_session.query(Talla).first()

    calzado = srv.registrarCalzado("PAM-016", marca.id, modelo.id, color.id, tipo.id, talla.id)
    assert calzado.id is not None
    assert calzado.activo is True


def test_cp06_calzado_combinacion_duplicada(db_session):
    srv = CatalogoService(db_session)
    marca = db_session.query(Marca).first()
    modelo = db_session.query(Modelo).first()
    color = db_session.query(Color).first()
    tipo = db_session.query(TipoCalzado).first()
    talla = db_session.query(Talla).first()

    srv.registrarCalzado("PAM-016", marca.id, modelo.id, color.id, tipo.id, talla.id)
    with pytest.raises(ReglaNegocioException) as exc:
        srv.registrarCalzado("PAM-016-B", marca.id, modelo.id, color.id, tipo.id, talla.id)
    assert "E1: Combinación Duplicada" in str(exc.value)