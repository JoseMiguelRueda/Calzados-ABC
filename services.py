from datetime import date
from werkzeug.security import generate_password_hash, check_password_hash
from sqlalchemy.exc import IntegrityError
from database import (
    Persona, Usuario, Cliente, Compromiso,
    Marca, Modelo, Color, TipoCalzado, Talla, Calzado
)


class ReglaNegocioException(Exception):
    def __init__(self, codigo, mensaje):
        self.codigo = codigo
        self.mensaje = mensaje
        super().__init__(f"{codigo}: {mensaje}")


class ControladorAcceso:
    def __init__(self, session):
        self.session = session

    def autenticar(self, login, password):
        usuario = self.session.query(Usuario).filter_by(login=login).first()
        if not usuario or not check_password_hash(usuario.password, password):
            raise ReglaNegocioException("AUTH-01", "Credenciales inválidas")
        if not usuario.activo:
            raise ReglaNegocioException("AUTH-02", "Cuenta suspendida")
        return usuario


class ClienteService:
    def __init__(self, session):
        self.session = session

    def registrarClienteConAval(self, nombre, nit, telefono, direccion, razon_social,
                                codigo_documento, fecha_firma, archivo_pdf,
                                login, password, aval_vigente=True):
        persona = Persona(nombre=nombre, nit=nit, telefono=telefono, direccion=direccion)
        self.session.add(persona)
        self.session.flush()

        estado_aval = "Vigente" if aval_vigente else "Pendiente"
        cliente = Cliente(id=persona.id, razon_social=razon_social, estado_aval=estado_aval)
        self.session.add(cliente)

        compromiso = Compromiso(
            cliente_id=persona.id,
            codigo_documento=codigo_documento,
            fecha_firma=fecha_firma or date.today(),
            archivo_pdf=archivo_pdf,
            vigente=aval_vigente
        )
        self.session.add(compromiso)

        usuario = Usuario(
            id=persona.id,
            login=login,
            password=generate_password_hash(password),
            rol="Cliente Mayorista",
            activo=aval_vigente
        )
        self.session.add(usuario)
        self.session.commit()
        return cliente

    def renovarAval(self, cliente_id, codigo_documento, nueva_fecha_firma, archivo_pdf):
        cliente = self.session.query(Cliente).filter_by(id=cliente_id).first()
        if not cliente:
            raise ReglaNegocioException("CLI-01", "Cliente no encontrado")

        for comp in cliente.compromisos:
            comp.vigente = False

        nuevo_comp = Compromiso(
            cliente_id=cliente.id,
            codigo_documento=codigo_documento,
            fecha_firma=nueva_fecha_firma,
            archivo_pdf=archivo_pdf,
            vigente=True
        )
        cliente.estado_aval = "Vigente"
        if cliente.persona.usuario:
            cliente.persona.usuario.activo = True

        self.session.add(nuevo_comp)
        self.session.commit()
        return cliente

    def validarPermisoPedido(self, cliente_id):
        cliente = self.session.query(Cliente).filter_by(id=cliente_id).first()
        tiene_compromiso_vigente = any(c.vigente for c in cliente.compromisos) if cliente else False
        if not cliente or cliente.estado_aval != "Vigente" or not tiene_compromiso_vigente:
            raise ReglaNegocioException("E1", "Cliente sin aval comercial vigente. No puede realizar pedidos.")
        return True


class CatalogoService:
    def __init__(self, session):
        self.session = session

    def esCombinacionDuplicada(self, marca_id, modelo_id, color_id, talla_id, excluir_id=None):
        query = self.session.query(Calzado).filter_by(
            marca_id=int(marca_id),
            modelo_id=int(modelo_id),
            color_id=int(color_id),
            talla_id=int(talla_id)
        )
        if excluir_id is not None:
            query = query.filter(Calzado.id != excluir_id)
        return query.first() is not None

    def registrarCalzado(self, codigo, marca_id, modelo_id, color_id, tipo_calzado_id, talla_id):
        # RN-01: Combinación única por FK normalizadas (marca_id, modelo_id, color_id, talla_id)
        if self.esCombinacionDuplicada(marca_id, modelo_id, color_id, talla_id):
            raise ReglaNegocioException("E1", "Combinación Duplicada (Marca + Modelo + Color + Talla)")

        modelo = self.session.query(Modelo).filter_by(id=int(modelo_id)).first()
        if not modelo or modelo.marca_id != int(marca_id):
            raise ReglaNegocioException("E2", "El modelo seleccionado no pertenece a la marca indicada.")

        calzado = Calzado(
            codigo=codigo.strip(),
            marca_id=int(marca_id),
            modelo_id=int(modelo_id),
            color_id=int(color_id),
            tipo_calzado_id=int(tipo_calzado_id),
            talla_id=int(talla_id),
            activo=True
        )
        self.session.add(calzado)
        try:
            self.session.commit()
        except IntegrityError:
            self.session.rollback()
            raise ReglaNegocioException("E1", "Combinación Duplicada (Marca + Modelo + Color + Talla) o Código repetido")
        return calzado

    def darBajaLogica(self, calzado_id):
        calzado = self.session.query(Calzado).filter_by(id=calzado_id).first()
        if not calzado:
            raise ReglaNegocioException("CAT-01", "Calzado no encontrado")
        calzado.activo = False
        self.session.commit()
        return calzado