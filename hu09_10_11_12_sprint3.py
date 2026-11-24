from datetime import datetime
from flask import Blueprint, render_template, request, redirect, url_for, session, flash, current_app
from sqlalchemy import inspect, text
from werkzeug.security import generate_password_hash
from database import (
    Almacen, Calzado, StockAlmacen, AjusteInventario,
    Persona, Usuario, Pedido, Cliente
)
from comunes import ReglaNegocioException, login_required

sprint3_bp = Blueprint("sprint3", __name__)


def asegurar_columna_almacen_activo(db_session):
    try:
        insp = inspect(db_session.bind)
        cols = [c["name"] for c in insp.get_columns("Almacen")]
        if "activo" not in cols:
            db_session.execute(text("ALTER TABLE Almacen ADD COLUMN activo BOOLEAN NOT NULL DEFAULT 1"))
            db_session.commit()
    except Exception:
        db_session.rollback()


def asegurar_columna_pedido_actualizacion(db_session):
    try:
        insp = inspect(db_session.bind)
        cols = [c["name"] for c in insp.get_columns("Pedido")]
        if "fecha_actualizacion" not in cols:
            db_session.execute(text("ALTER TABLE Pedido ADD COLUMN fecha_actualizacion DATETIME"))
            db_session.commit()
    except Exception:
        db_session.rollback()


class Sprint3Service:
    def __init__(self, db_session):
        self.session = db_session
        asegurar_columna_almacen_activo(self.session)
        asegurar_columna_pedido_actualizacion(self.session)

    def _sincronizarTotalCalzado(self, calzado):
        if not calzado:
            return
        total = sum(
            int(s.cantidad or 0)
            for s in self.session.query(StockAlmacen).filter_by(calzado_id=calzado.id).all()
        )
        calzado.stock_disponible = total

    # HU-09: Registro de ajustes de inventario por mermas y diferencias
    def registrarAjusteInventario(self, almacen_id, calzado_id, stock_fisico, motivo):
        almacen = self.session.query(Almacen).filter_by(id=int(almacen_id)).first()
        if not almacen:
            raise ReglaNegocioException("AJU-01", "Almacén no encontrado.")
        if not getattr(almacen, "activo", True):
            raise ReglaNegocioException("AJU-02", "No se pueden realizar ajustes en un almacén inactivo.")

        calzado = self.session.query(Calzado).filter_by(id=int(calzado_id)).first()
        if not calzado:
            raise ReglaNegocioException("AJU-03", "Calzado no encontrado.")

        motivo_limpio = (motivo or "").strip()
        if not motivo_limpio:
            raise ReglaNegocioException("AJU-04", "Debe indicar el motivo o justificación de merma/diferencia.")

        try:
            fisico_val = int(stock_fisico)
        except (TypeError, ValueError):
            raise ReglaNegocioException("AJU-05", "El conteo físico debe ser un número entero.")

        if fisico_val < 0:
            raise ReglaNegocioException("AJU-06", "El stock físico no puede ser negativo.")

        st = self.session.query(StockAlmacen).filter_by(
            almacen_id=almacen.id, calzado_id=calzado.id
        ).first()
        if not st:
            st = StockAlmacen(almacen_id=almacen.id, calzado_id=calzado.id, cantidad=0)
            self.session.add(st)
            self.session.flush()

        anterior_val = int(st.cantidad or 0)
        diferencia = fisico_val - anterior_val

        if diferencia == 0:
            raise ReglaNegocioException("AJU-00", "No hay diferencia en el stock")

        st.cantidad = fisico_val
        self._sincronizarTotalCalzado(calzado)

        ajuste = AjusteInventario(
            codigo_ajuste=f"AJU-{datetime.utcnow().strftime('%Y%m%d%H%M%S%f')[-10:]}",
            almacen_id=almacen.id,
            calzado_id=calzado.id,
            stock_anterior=anterior_val,
            stock_fisico=fisico_val,
            diferencia=diferencia,
            motivo=motivo_limpio
        )
        self.session.add(ajuste)
        self.session.commit()
        return ajuste

    # HU-10: Configuración de sucursales y almacenes
    def registrarAlmacen(self, nombre, ubicacion="", es_central=False, activo=True):
        nombre_limpio = (nombre or "").strip()
        if not nombre_limpio:
            raise ReglaNegocioException("ALM-02", "El nombre del almacén o sucursal es obligatorio.")
        if self.session.query(Almacen).filter(Almacen.nombre.ilike(nombre_limpio)).first():
            raise ReglaNegocioException("ALM-03", f"Ya existe un almacén llamado '{nombre_limpio}'.")

        alm = Almacen(
            nombre=nombre_limpio,
            ubicacion=(ubicacion or "").strip(),
            es_central=bool(es_central),
            activo=bool(activo)
        )
        self.session.add(alm)
        self.session.flush()

        for cal in self.session.query(Calzado).all():
            self.session.add(StockAlmacen(almacen_id=alm.id, calzado_id=cal.id, cantidad=0))

        self.session.commit()
        return alm

    def editarAlmacen(self, almacen_id, nombre, ubicacion="", es_central=False, activo=True):
        alm = self.session.query(Almacen).filter_by(id=int(almacen_id)).first()
        if not alm:
            raise ReglaNegocioException("ALM-04", "Almacén no encontrado.")
        nombre_limpio = (nombre or "").strip()
        if not nombre_limpio:
            raise ReglaNegocioException("ALM-02", "El nombre del almacén es obligatorio.")
        duplicado = self.session.query(Almacen).filter(
            Almacen.nombre.ilike(nombre_limpio),
            Almacen.id != alm.id
        ).first()
        if duplicado:
            raise ReglaNegocioException("ALM-03", f"Ya existe otro almacén llamado '{nombre_limpio}'.")

        alm.nombre = nombre_limpio
        alm.ubicacion = (ubicacion or "").strip()
        alm.es_central = bool(es_central)
        alm.activo = bool(activo)
        self.session.commit()
        return alm

    def cambiarEstadoAlmacen(self, almacen_id, activo):
        alm = self.session.query(Almacen).filter_by(id=int(almacen_id)).first()
        if not alm:
            raise ReglaNegocioException("ALM-04", "Almacén no encontrado.")
        alm.activo = bool(activo)
        self.session.commit()
        return alm

    # HU-11: Gestión de usuarios internos de empleados
    def crearUsuarioInterno(self, nombre, nit, telefono, direccion, login, password, rol, activo=True):
        roles_internos = ("Administrador", "Encargado de Pedidos", "Encargado de Almacén")
        if rol not in roles_internos:
            raise ReglaNegocioException("USR-01", "Rol interno no válido.")
        login_limpio = (login or "").strip().lower()
        if not login_limpio or not password:
            raise ReglaNegocioException("USR-02", "El correo/login y contraseña son obligatorios.")
        if self.session.query(Usuario).filter(Usuario.login.ilike(login_limpio)).first():
            raise ReglaNegocioException("USR-03", f"El usuario '{login_limpio}' ya existe.")

        persona = Persona(
            nombre=(nombre or "").strip(),
            nit=(nit or "").strip(),
            telefono=(telefono or "").strip(),
            direccion=(direccion or "").strip()
        )
        self.session.add(persona)
        self.session.flush()

        usuario = Usuario(
            id=persona.id,
            login=login_limpio,
            password=generate_password_hash(password),
            rol=rol,
            activo=bool(activo)
        )
        self.session.add(usuario)
        self.session.commit()
        return usuario

    def eliminarUsuarioInterno(self, usuario_id, usuario_actual_id=None):
        uid = int(usuario_id)
        if usuario_actual_id is not None and uid == int(usuario_actual_id):
            raise ReglaNegocioException("USR-05", "No puedes eliminar tu propio usuario en sesión.")
        usuario = self.session.query(Usuario).filter_by(id=uid).first()
        if not usuario:
            raise ReglaNegocioException("USR-04", "Usuario interno no encontrado.")
        persona = usuario.persona
        self.session.delete(usuario)
        if persona and not persona.cliente:
            self.session.delete(persona)
        self.session.commit()

    def actualizarUsuarioInterno(self, usuario_id, rol, activo):
        roles_internos = ("Administrador", "Encargado de Pedidos", "Encargado de Almacén")
        if rol not in roles_internos:
            raise ReglaNegocioException("USR-01", "Rol interno no válido.")
        usuario = self.session.query(Usuario).filter_by(id=int(usuario_id)).first()
        if not usuario:
            raise ReglaNegocioException("USR-04", "Usuario interno no encontrado.")
        usuario.rol = rol
        usuario.activo = bool(activo)
        self.session.commit()
        return usuario


@sprint3_bp.route("/ajustes-inventario", methods=["GET", "POST"])
@login_required(roles=["Administrador", "Encargado de Almacén"])
def ajustes_inventario():
    db = current_app.config["DB_SESSION"]
    srv = Sprint3Service(db)
    try:
        if request.method == "POST":
            try:
                ajuste = srv.registrarAjusteInventario(
                    almacen_id=request.form.get("almacen_id"),
                    calzado_id=request.form.get("calzado_id"),
                    stock_fisico=request.form.get("stock_fisico"),
                    motivo=request.form.get("motivo", "")
                )
                signo = "+" if ajuste.diferencia > 0 else ""
                flash(
                    f"Nota de Ajuste {ajuste.codigo_ajuste} emitida ({signo}{ajuste.diferencia} uds) en {ajuste.almacen.nombre}.",
                    "success"
                )
            except ReglaNegocioException as e:
                db.rollback()
                flash(str(e), "warning" if e.codigo == "AJU-00" else "danger")
            except Exception as e:
                db.rollback()
                flash(f"Error al registrar ajuste: {str(e)}", "danger")
            return redirect(url_for("sprint3.ajustes_inventario"))

        return render_template(
            "ajustes_inventario.html",
            almacenes=db.query(Almacen).order_by(Almacen.id).all(),
            calzados=db.query(Calzado).order_by(Calzado.codigo).all(),
            stocks=db.query(StockAlmacen).all(),
            ajustes=db.query(AjusteInventario).order_by(AjusteInventario.id.desc()).all()
        )
    finally:
        db.remove()


@sprint3_bp.route("/sucursales", methods=["GET", "POST"])
@login_required(roles=["Administrador"])
def sucursales():
    db = current_app.config["DB_SESSION"]
    srv = Sprint3Service(db)
    try:
        if request.method == "POST":
            accion = request.form.get("accion")
            try:
                if accion == "crear":
                    alm = srv.registrarAlmacen(
                        nombre=request.form.get("nombre", ""),
                        ubicacion=request.form.get("ubicacion", ""),
                        es_central=(request.form.get("es_central") == "on"),
                        activo=(request.form.get("activo", "on") == "on")
                    )
                    flash(f"Sucursal/Almacén '{alm.nombre}' registrado y habilitado.", "success")
                elif accion == "editar":
                    alm = srv.editarAlmacen(
                        almacen_id=request.form.get("almacen_id"),
                        nombre=request.form.get("nombre", ""),
                        ubicacion=request.form.get("ubicacion", ""),
                        es_central=(request.form.get("es_central") == "on"),
                        activo=(request.form.get("activo") == "on")
                    )
                    flash(f"Almacén '{alm.nombre}' actualizado.", "success")
                elif accion == "toggle_estado":
                    alm = srv.cambiarEstadoAlmacen(
                        almacen_id=request.form.get("almacen_id"),
                        activo=(request.form.get("activo") == "1")
                    )
                    estado_txt = "operativo" if alm.activo else "inactivo"
                    flash(f"Almacén '{alm.nombre}' marcado como {estado_txt}.", "warning")
            except ReglaNegocioException as e:
                db.rollback()
                flash(str(e), "danger")
            except Exception as e:
                db.rollback()
                flash(f"Error en sucursal/almacén: {str(e)}", "danger")
            return redirect(url_for("sprint3.sucursales"))

        return render_template(
            "sucursales.html",
            almacenes=db.query(Almacen).order_by(Almacen.id).all()
        )
    finally:
        db.remove()


@sprint3_bp.route("/usuarios-internos", methods=["GET", "POST"])
@login_required(roles=["Administrador"])
def usuarios_internos():
    db = current_app.config["DB_SESSION"]
    srv = Sprint3Service(db)
    roles_internos = ["Administrador", "Encargado de Pedidos", "Encargado de Almacén"]
    try:
        if request.method == "POST":
            accion = request.form.get("accion")
            try:
                if accion == "crear":
                    usr = srv.crearUsuarioInterno(
                        nombre=request.form.get("nombre", ""),
                        nit=request.form.get("nit", ""),
                        telefono=request.form.get("telefono", ""),
                        direccion=request.form.get("direccion", ""),
                        login=request.form.get("login", ""),
                        password=request.form.get("password", ""),
                        rol=request.form.get("rol", ""),
                        activo=(request.form.get("activo", "on") == "on")
                    )
                    flash(f"Usuario interno '{usr.login}' creado con rol {usr.rol}.", "success")
                elif accion == "eliminar":
                    srv.eliminarUsuarioInterno(
                        usuario_id=request.form.get("usuario_id"),
                        usuario_actual_id=session.get("user_id")
                    )
                    flash("Usuario interno eliminado.", "warning")
                elif accion == "actualizar":
                    usr = srv.actualizarUsuarioInterno(
                        usuario_id=request.form.get("usuario_id"),
                        rol=request.form.get("rol", ""),
                        activo=(request.form.get("activo") == "1")
                    )
                    flash(f"Usuario '{usr.login}' actualizado (Rol: {usr.rol}, Activo: {usr.activo}).", "info")
            except ReglaNegocioException as e:
                db.rollback()
                flash(str(e), "danger")
            except Exception as e:
                db.rollback()
                flash(f"Error al gestionar usuario: {str(e)}", "danger")
            return redirect(url_for("sprint3.usuarios_internos"))

        usuarios = db.query(Usuario).filter(Usuario.rol.in_(roles_internos)).order_by(Usuario.id).all()
        return render_template(
            "usuarios_internos.html",
            usuarios=usuarios,
            roles_internos=roles_internos
        )
    finally:
        db.remove()


@sprint3_bp.route("/historial-pedidos", methods=["GET"])
@login_required(roles=["Administrador", "Encargado de Pedidos", "Cliente Mayorista"])
def historial_pedidos():
    db = current_app.config["DB_SESSION"]
    asegurar_columna_pedido_actualizacion(db)
    try:
        rol = session.get("rol")
        user_id = session.get("user_id")
        estado_filtro = request.args.get("estado", "").strip()
        pedido_sel_id = request.args.get("pedido_id", "").strip()

        query = db.query(Pedido)
        if rol == "Cliente Mayorista":
            query = query.filter_by(cliente_id=user_id)
        if estado_filtro:
            query = query.filter_by(estado=estado_filtro)

        lista_pedidos = query.order_by(Pedido.id.desc()).all()
        pedido_detalle = None
        if pedido_sel_id.isdigit():
            pedido_detalle = db.query(Pedido).filter_by(id=int(pedido_sel_id)).first()
            if pedido_detalle and rol == "Cliente Mayorista" and pedido_detalle.cliente_id != user_id:
                pedido_detalle = None

        return render_template(
            "historial_pedidos.html",
            pedidos=lista_pedidos,
            pedido_detalle=pedido_detalle,
            estado_filtro=estado_filtro,
            estados_disponibles=["Pendiente", "Reservado", "Confirmado", "En Tránsito", "Entregado", "Anulado"]
        )
    finally:
        db.remove()
