from functools import wraps
from flask import session, redirect, url_for, flash


class ReglaNegocioException(Exception):
    def __init__(self, codigo, mensaje):
        self.codigo = codigo
        self.mensaje = mensaje
        super().__init__(f"{codigo}: {mensaje}")


def login_required(roles=None):
    def decorator(f):
        @wraps(f)
        def wrapper(*args, **kwargs):
            if "user_id" not in session:
                return redirect(url_for("hu01.login"))
            if roles and session.get("rol") not in roles:
                flash("Acceso denegado: no tiene permisos para este módulo (RNF-02).", "danger")
                return redirect(url_for("hu01.dashboard"))
            return f(*args, **kwargs)
        return wrapper
    return decorator
