import os
from datetime import date
from functools import wraps
from flask import Flask, render_template, request, redirect, url_for, session, flash
from werkzeug.security import generate_password_hash
from werkzeug.utils import secure_filename

from database import (
    get_session, Persona, Usuario, Cliente,
    Marca, Modelo, Color, TipoCalzado, Talla, Calzado
)
from services import ControladorAcceso, ClienteService, CatalogoService, ReglaNegocioException


def create_app(db_url="sqlite:///calzados_abc.db"):
    app = Flask(__name__)
    app.secret_key = "calzados_abc_sprint1_secret_key"
    app.config["UPLOAD_FOLDER"] = os.path.join(os.path.dirname(__file__), "uploads")
    os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)

    db = get_session(db_url)
    seed_data(db)

    def login_required(roles=None):
        def decorator(f):
            @wraps(f)
            def wrapper(*args, **kwargs):
                if "user_id" not in session:
                    return redirect(url_for("login"))
                if roles and session.get("rol") not in roles:
                    flash("Acceso denegado: no tiene permisos para este módulo (RNF-02).", "danger")
                    return redirect(url_for("dashboard"))
                return f(*args, **kwargs)
            return wrapper
        return decorator

    @app.route("/")
    def index():
        return redirect(url_for("dashboard") if "user_id" in session else url_for("login"))

    @app.route("/login", methods=["GET", "POST"])
    def login():
        if request.method == "POST":
            auth = ControladorAcceso(db)
            try:
                user = auth.autenticar(request.form.get("login", "").strip(), request.form.get("password", ""))
                session["user_id"] = user.id
                session["nombre"] = user.persona.nombre
                session["rol"] = user.rol
                return redirect(url_for("dashboard"))
            except ReglaNegocioException as e:
                flash(e.mensaje, "danger")
        return render_template("login.html")

    @app.route("/logout")
    def logout():
        session.clear()
        return redirect(url_for("login"))

    @app.route("/dashboard")
    @login_required()
    def dashboard():
        return render_template(
            "dashboard.html",
            total_clientes=db.query(Cliente).count(),
            total_calzados=db.query(Calzado).count()
        )

    @app.route("/clientes", methods=["GET", "POST"])
    @login_required(roles=["Administrador"])
    def clientes():
        cliente_srv = ClienteService(db)
        if request.method == "POST":
            accion = request.form.get("accion")
            try:
                if accion == "crear":
                    pdf_file = request.files.get("archivo_pdf")
                    filename = ""
                    if pdf_file and pdf_file.filename:
                        filename = secure_filename(pdf_file.filename)
                        pdf_file.save(os.path.join(app.config["UPLOAD_FOLDER"], filename))

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
            return redirect(url_for("clientes"))

        return render_template("clientes.html", clientes=db.query(Cliente).all())

    @app.route("/catalogo", methods=["GET", "POST"])
    @login_required(roles=["Administrador", "Cliente Mayorista"])
    def catalogo():
        catalogo_srv = CatalogoService(db)
        if request.method == "POST":
            if session.get("rol") != "Administrador":
                flash("Solo el Administrador puede modificar el catálogo.", "danger")
                return redirect(url_for("catalogo"))
            accion = request.form.get("accion")
            try:
                # --- Calzado ---
                if accion == "crear":
                    catalogo_srv.registrarCalzado(
                        codigo=request.form.get("codigo"),
                        marca_id=request.form.get("marca_id"),
                        modelo_id=request.form.get("modelo_id"),
                        color_id=request.form.get("color_id"),
                        tipo_calzado_id=request.form.get("tipo_calzado_id"),
                        talla_id=request.form.get("talla_id")
                    )
                    flash("Calzado registrado en catálogo como Activo.", "success")
                elif accion == "baja":
                    catalogo_srv.darBajaLogica(int(request.form.get("calzado_id")))
                    flash("Calzado dado de baja lógica (Inactivo).", "warning")
                elif accion == "eliminar":
                    catalogo_srv.eliminarCalzado(int(request.form.get("calzado_id")))
                    flash("Calzado eliminado del catálogo.", "warning")

                # --- Agregar opciones de tablas descriptivas desde el mismo catálogo ---
                elif accion == "agregar_marca":
                    catalogo_srv.agregarMarca(request.form.get("nombre", ""))
                    flash("Marca agregada.", "success")
                elif accion == "agregar_modelo":
                    catalogo_srv.agregarModelo(request.form.get("marca_id"), request.form.get("nombre", ""))
                    flash("Modelo agregado a la marca.", "success")
                elif accion == "agregar_color":
                    catalogo_srv.agregarColor(request.form.get("color", ""))
                    flash("Color agregado.", "success")
                elif accion == "agregar_tipo":
                    catalogo_srv.agregarTipoCalzado(request.form.get("descripcion", ""))
                    flash("Tipo de calzado agregado.", "success")
                elif accion == "agregar_talla":
                    catalogo_srv.agregarTalla(
                        eu=request.form.get("eu", ""),
                        usa=request.form.get("usa", ""),
                        jp=request.form.get("jp", ""),
                        br=request.form.get("br", ""),
                        cm=request.form.get("cm", "")
                    )
                    flash("Talla agregada.", "success")

                # --- Borrar el ítem específico seleccionado desde el botón basurero ---
                elif accion == "eliminar_marca":
                    catalogo_srv.eliminarMarca(request.form.get("id"))
                    flash("Marca eliminada.", "warning")
                elif accion == "eliminar_modelo":
                    catalogo_srv.eliminarModelo(request.form.get("id"))
                    flash("Modelo eliminado.", "warning")
                elif accion == "eliminar_color":
                    catalogo_srv.eliminarColor(request.form.get("id"))
                    flash("Color eliminado.", "warning")
                elif accion == "eliminar_tipo":
                    catalogo_srv.eliminarTipoCalzado(request.form.get("id"))
                    flash("Tipo de calzado eliminado.", "warning")
                elif accion == "eliminar_talla":
                    catalogo_srv.eliminarTalla(request.form.get("id"))
                    flash("Talla eliminada.", "warning")

            except ReglaNegocioException as e:
                db.rollback()
                flash(str(e), "danger")
            except Exception as e:
                db.rollback()
                flash(f"Error: {str(e)}", "danger")
            return redirect(url_for("catalogo"))

        return render_template(
            "catalogo.html",
            marcas=db.query(Marca).order_by(Marca.nombre).all(),
            modelos=db.query(Modelo).order_by(Modelo.marca_id, Modelo.nombre).all(),
            colores=db.query(Color).order_by(Color.color).all(),
            tipos=db.query(TipoCalzado).order_by(TipoCalzado.descripcion).all(),
            tallas=db.query(Talla).order_by(Talla.eu).all(),
            calzados=db.query(Calzado).all()
        )

    return app


def seed_data(db):
    if db.query(TipoCalzado).count() == 0:
        for desc in ["Sandalias", "Tenis", "Zapato Formal", "Botines"]:
            db.add(TipoCalzado(descripcion=desc))
        db.commit()

    if db.query(Marca).count() == 0:
        pampili = Marca(nombre="Pampili")
        molekinha = Marca(nombre="Molekinha")
        db.add_all([pampili, molekinha])
        db.flush()
        db.add_all([
            Modelo(marca_id=pampili.id, nombre="016"),
            Modelo(marca_id=pampili.id, nombre="024"),
            Modelo(marca_id=molekinha.id, nombre="2157")
        ])
        db.commit()

    if db.query(Color).count() == 0:
        db.add_all([Color(color="Negro"), Color(color="Blanco"), Color(color="Rosa")])
        db.commit()

    if db.query(Talla).count() == 0:
        db.add_all([
            Talla(eu="27", usa="10", jp="16.5", br="25", cm="16.5"),
            Talla(eu="28", usa="11", jp="17.5", br="26", cm="17.5")
        ])
        db.commit()

    if not db.query(Usuario).filter_by(login="admin@abc.com").first():
        persona = Persona(
            nombre="Administrador General ABC",
            nit="1020304050",
            telefono="70012345",
            direccion="Av. Brasil #500 - Almacén Central"
        )
        db.add(persona)
        db.flush()
        db.add(Usuario(
            id=persona.id,
            login="admin@abc.com",
            password=generate_password_hash("admin123"),
            rol="Administrador",
            activo=True
        ))
        db.commit()

    if db.query(Calzado).count() == 0:
        pampili = db.query(Marca).filter_by(nombre="Pampili").first()
        mod016 = db.query(Modelo).filter_by(nombre="016").first()
        negro = db.query(Color).filter_by(color="Negro").first()
        sandalia = db.query(TipoCalzado).filter_by(descripcion="Sandalias").first()
        talla27 = db.query(Talla).filter_by(eu="27").first()
        db.add(Calzado(
            codigo="PAM-016-NEG-27",
            marca_id=pampili.id,
            modelo_id=mod016.id,
            color_id=negro.id,
            tipo_calzado_id=sandalia.id,
            talla_id=talla27.id,
            activo=True
        ))
        db.commit()


if __name__ == "__main__":
    app = create_app()
    app.run(debug=True, port=8080)