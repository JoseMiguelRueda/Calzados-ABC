import os
from datetime import date
from flask import Blueprint, render_template, request, redirect, url_for, flash, current_app
from werkzeug.security import generate_password_hash
from werkzeug.utils import secure_filename
from database import Persona, Usuario, Cliente, Compromiso
from comunes import ReglaNegocioException, login_required

hu02_bp = Blueprint("hu02", __name__)


class ClienteService:
    def __init__(self, db_session):
        self.session = db_session

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


@hu02_bp.route("/clientes", methods=["GET", "POST"])
@login_required(roles=["Administrador"])
def clientes():
    db = current_app.config["DB_SESSION"]
    cliente_srv = ClienteService(db)
    if request.method == "POST":
        accion = request.form.get("accion")
        try:
            if accion == "crear":
                pdf_file = request.files.get("archivo_pdf")
                filename = ""
                if pdf_file and pdf_file.filename:
                    filename = secure_filename(pdf_file.filename)
                    pdf_file.save(os.path.join(current_app.config["UPLOAD_FOLDER"], filename))

                fecha_str = request.form.get("fecha_firma")
                cliente_srv.registrarClienteConAval(
                    nombre=request.form.get("nombre"),
                    nit=request.form.get("nit"),
                    telefono=request.form.get("telefono"),
                    direccion=request.form.get("direccion"),
                    razon_social=request.form.get("razon_social"),
                    codigo_documento=request.form.get("codigo_documento"),
                    fecha_firma=date.fromisoformat(fecha_str) if fecha_str else date.today(),
                    archivo_pdf=filename,
                    login=request.form.get("login"),
                    password=request.form.get("password"),
                    aval_vigente=(request.form.get("aval_vigente") == "on")
                )
                flash("Cliente mayorista registrado correctamente.", "success")
            elif accion == "renovar":
                fecha_str = request.form.get("nueva_fecha_firma")
                cliente_srv.renovarAval(
                    cliente_id=int(request.form.get("cliente_id")),
                    codigo_documento=request.form.get("codigo_documento"),
                    nueva_fecha_firma=date.fromisoformat(fecha_str) if fecha_str else date.today(),
                    archivo_pdf="renovacion.pdf"
                )
                flash("Aval comercial renovado a Vigente.", "success")
        except Exception as e:
            db.rollback()
            flash(f"Error al procesar cliente: {str(e)}", "danger")
        return redirect(url_for("hu02.clientes"))

    return render_template("clientes.html", clientes=db.query(Cliente).all())
