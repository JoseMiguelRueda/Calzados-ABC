from flask import Blueprint, render_template, request, redirect, url_for, session, flash, current_app
from werkzeug.security import check_password_hash
from database import Usuario, Cliente, Calzado
from comunes import ReglaNegocioException, login_required

hu01_bp = Blueprint("hu01", __name__)


class ControladorAcceso:
    def __init__(self, db_session):
        self.session = db_session

    def autenticar(self, login, password):
        usuario = self.session.query(Usuario).filter_by(login=login).first()
        if not usuario or not check_password_hash(usuario.password, password):
            raise ReglaNegocioException("AUTH-01", "Credenciales inválidas")
        if not usuario.activo:
            raise ReglaNegocioException("AUTH-02", "Cuenta suspendida")
        return usuario


@hu01_bp.route("/")
def index():
    return redirect(url_for("hu01.dashboard") if "user_id" in session else url_for("hu01.login"))


@hu01_bp.route("/login", methods=["GET", "POST"])
def login():
    db = current_app.config["DB_SESSION"]
    if request.method == "POST":
        auth = ControladorAcceso(db)
        try:
            user = auth.autenticar(request.form.get("login", "").strip(), request.form.get("password", ""))
            session["user_id"] = user.id
            session["nombre"] = user.persona.nombre
            session["rol"] = user.rol
            return redirect(url_for("hu01.dashboard"))
        except ReglaNegocioException as e:
            flash(e.mensaje, "danger")
    return render_template("login.html")


@hu01_bp.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("hu01.login"))


@hu01_bp.route("/dashboard")
@login_required()
def dashboard():
    db = current_app.config["DB_SESSION"]
    return render_template(
        "dashboard.html",
        total_clientes=db.query(Cliente).count(),
        total_calzados=db.query(Calzado).count()
    )
