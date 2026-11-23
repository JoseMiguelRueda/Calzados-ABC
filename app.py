import os
from flask import Flask
from werkzeug.security import generate_password_hash

from database import (
    get_session, Persona, Usuario,
    Marca, Modelo, Color, TipoCalzado, Talla, Calzado, Almacen, StockAlmacen
)
from hu01_acceso import hu01_bp
from hu02_clientes import hu02_bp
from hu03_catalogo import hu03_bp
from hu04_pedidos import hu04_bp
from hu07_almacenes import hu07_bp


def create_app(db_url="sqlite:///calzados_abc.db"):
    app = Flask(__name__)
    app.secret_key = "calzados_abc_sprint2_full_secret_key"
    app.config["UPLOAD_FOLDER"] = os.path.join(os.path.dirname(__file__), "uploads")
    os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)

    db = get_session(db_url)
    app.config["DB_SESSION"] = db
    seed_data(db)
    sync_stocks_with_catalog(db)

    app.register_blueprint(hu01_bp)
    app.register_blueprint(hu02_bp)
    app.register_blueprint(hu03_bp)
    app.register_blueprint(hu04_bp)
    app.register_blueprint(hu07_bp)


    @app.teardown_appcontext
    def cleanup_session(exception=None):
        db.remove()

    return app



def sync_stocks_with_catalog(db):
    from database import Almacen, StockAlmacen, Calzado
    almacenes = db.query(Almacen).order_by(Almacen.id).all()
    if not almacenes:
        return
    central = next((a for a in almacenes if a.es_central), almacenes[0])
    calzados = db.query(Calzado).all()
    for cal in calzados:
        stocks_cal = db.query(StockAlmacen).filter_by(calzado_id=cal.id).all()
        if not stocks_cal:
            for alm in almacenes:
                cant = int(cal.stock_disponible or 0) if alm.id == central.id else 0
                db.add(StockAlmacen(almacen_id=alm.id, calzado_id=cal.id, cantidad=cant))
            db.flush()
            stocks_cal = db.query(StockAlmacen).filter_by(calzado_id=cal.id).all()
        cal.stock_disponible = sum(int(s.cantidad or 0) for s in stocks_cal)
    db.commit()


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

    if db.query(Almacen).count() == 0:
        central = Almacen(nombre="Almacén Central", ubicacion="Av. Brasil #500", es_central=True)
        sucursal = Almacen(nombre="Almacén Sucursal Norte", ubicacion="Av. Banzer Km 6", es_central=False)
        db.add_all([central, sucursal])
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

    if not db.query(Usuario).filter_by(login="encargado@abc.com").first():
        persona_enc = Persona(
            nombre="Encargado de Pedidos ABC",
            nit="1020304099",
            telefono="70099887",
            direccion="Av. Brasil #500 - Despacho"
        )
        db.add(persona_enc)
        db.flush()
        db.add(Usuario(
            id=persona_enc.id,
            login="encargado@abc.com",
            password=generate_password_hash("encargado123"),
            rol="Encargado de Pedidos",
            activo=True
        ))
        db.commit()

    if db.query(Calzado).count() == 0:
        pampili = db.query(Marca).filter_by(nombre="Pampili").first()
        mod016 = db.query(Modelo).filter_by(nombre="016").first()
        negro = db.query(Color).filter_by(color="Negro").first()
        sandalia = db.query(TipoCalzado).filter_by(descripcion="Sandalias").first()
        talla27 = db.query(Talla).filter_by(eu="27").first()
        central = db.query(Almacen).filter_by(es_central=True).first()
        sucursal = db.query(Almacen).filter_by(es_central=False).first()

        cal = Calzado(
            codigo="PAM-016-NEG-27",
            marca_id=pampili.id,
            modelo_id=mod016.id,
            color_id=negro.id,
            tipo_calzado_id=sandalia.id,
            talla_id=talla27.id,
            precio_mayorista=135.0,
            stock_disponible=40,
            activo=True
        )
        db.add(cal)
        db.flush()
        db.add_all([
            StockAlmacen(almacen_id=central.id, calzado_id=cal.id, cantidad=30),
            StockAlmacen(almacen_id=sucursal.id, calzado_id=cal.id, cantidad=10),
        ])
        db.commit()


if __name__ == "__main__":
    app = create_app()
    app.run(debug=True, port=8080)
