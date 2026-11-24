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
from hu09_10_11_12_sprint3 import sprint3_bp


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
    app.register_blueprint(sprint3_bp)

    @app.teardown_appcontext
    def cleanup_session(exception=None):
        db.remove()

    return app


def sync_stocks_with_catalog(db):
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
        kidys = Marca(nombre="Kidys")
        db.add_all([pampili, molekinha, kidys])
        db.flush()
        db.add_all([
            Modelo(marca_id=pampili.id, nombre="016"),
            Modelo(marca_id=pampili.id, nombre="024"),
            Modelo(marca_id=molekinha.id, nombre="2157"),
            Modelo(marca_id=molekinha.id, nombre="3084"),
            Modelo(marca_id=kidys.id, nombre="5120")
        ])
        db.commit()

    if db.query(Color).count() == 0:
        db.add_all([
            Color(color="Negro"),
            Color(color="Blanco"),
            Color(color="Rosa"),
            Color(color="Azul")
        ])
        db.commit()

    if db.query(Talla).count() == 0:
        db.add_all([
            Talla(eu="24", usa="8", jp="14.5", br="22", cm="14.5"),
            Talla(eu="25", usa="8.5", jp="15.0", br="23", cm="15.0"),
            Talla(eu="26", usa="9.5", jp="15.8", br="24", cm="15.8"),
            Talla(eu="27", usa="10", jp="16.5", br="25", cm="16.5"),
            Talla(eu="28", usa="11", jp="17.5", br="26", cm="17.5"),
            Talla(eu="29", usa="11.5", jp="18.0", br="27", cm="18.0"),
            Talla(eu="30", usa="12.5", jp="18.8", br="28", cm="18.8"),
            Talla(eu="31", usa="13", jp="19.5", br="29", cm="19.5"),
            Talla(eu="32", usa="1", jp="20.2", br="30", cm="20.2")
        ])
        db.commit()

    if db.query(Almacen).count() == 0:
        db.add_all([
            Almacen(nombre="Feria Barrio Lindo", ubicacion="Feria Barrio Lindo - Santa Cruz", es_central=False, activo=True),
            Almacen(nombre="Mercado la Ramada", ubicacion="Mercado La Ramada - Santa Cruz", es_central=False, activo=True),
            Almacen(nombre="Mercado Los Pozos", ubicacion="Mercado Los Pozos - Santa Cruz", es_central=False, activo=True),
            Almacen(nombre="Mercado de Montero", ubicacion="Mercado Central - Montero", es_central=False, activo=True),
            Almacen(nombre="Central", ubicacion="Almacén Central - Santa Cruz", es_central=True, activo=True)
        ])
        db.commit()

    if not db.query(Usuario).filter_by(login="admin").first():
        persona = Persona(
            nombre="Administrador General ABC",
            nit="1020304050",
            telefono="70012345",
            direccion="Almacén Central - Santa Cruz"
        )
        db.add(persona)
        db.flush()
        db.add(Usuario(
            id=persona.id,
            login="admin",
            password=generate_password_hash("admin123"),
            rol="Administrador",
            activo=True
        ))
        db.commit()

    if not db.query(Usuario).filter_by(login="encargado").first():
        persona_enc = Persona(
            nombre="Encargado de Pedidos ABC",
            nit="1020304099",
            telefono="70099887",
            direccion="Almacén Central - Despacho"
        )
        db.add(persona_enc)
        db.flush()
        db.add(Usuario(
            id=persona_enc.id,
            login="encargado",
            password=generate_password_hash("encargado123"),
            rol="Encargado de Pedidos",
            activo=True
        ))
        db.commit()

    if not db.query(Usuario).filter_by(login="almacen").first():
        persona_alm = Persona(
            nombre="Encargado de Almacén ABC",
            nit="1020304088",
            telefono="70088776",
            direccion="Almacén Central - Inventario"
        )
        db.add(persona_alm)
        db.flush()
        db.add(Usuario(
            id=persona_alm.id,
            login="almacen",
            password=generate_password_hash("almacen123"),
            rol="Encargado de Almacén",
            activo=True
        ))
        db.commit()

    if db.query(Calzado).count() == 0:
        pampili = db.query(Marca).filter_by(nombre="Pampili").first()
        molekinha = db.query(Marca).filter_by(nombre="Molekinha").first()
        kidys = db.query(Marca).filter_by(nombre="Kidys").first()

        mod016 = db.query(Modelo).filter_by(nombre="016").first()
        mod024 = db.query(Modelo).filter_by(nombre="024").first()
        mod2157 = db.query(Modelo).filter_by(nombre="2157").first()
        mod3084 = db.query(Modelo).filter_by(nombre="3084").first()
        mod5120 = db.query(Modelo).filter_by(nombre="5120").first()

        negro = db.query(Color).filter_by(color="Negro").first()
        blanco = db.query(Color).filter_by(color="Blanco").first()
        rosa = db.query(Color).filter_by(color="Rosa").first()
        azul = db.query(Color).filter_by(color="Azul").first()

        sandalia = db.query(TipoCalzado).filter_by(descripcion="Sandalias").first()
        tenis = db.query(TipoCalzado).filter_by(descripcion="Tenis").first()
        formal = db.query(TipoCalzado).filter_by(descripcion="Zapato Formal").first()
        botines = db.query(TipoCalzado).filter_by(descripcion="Botines").first()

        talla26 = db.query(Talla).filter_by(eu="26").first()
        talla27 = db.query(Talla).filter_by(eu="27").first()
        talla28 = db.query(Talla).filter_by(eu="28").first()
        talla29 = db.query(Talla).filter_by(eu="29").first()
        talla30 = db.query(Talla).filter_by(eu="30").first()

        central = db.query(Almacen).filter_by(nombre="Central").first()
        barrio_lindo = db.query(Almacen).filter_by(nombre="Feria Barrio Lindo").first()
        ramada = db.query(Almacen).filter_by(nombre="Mercado la Ramada").first()
        pozos = db.query(Almacen).filter_by(nombre="Mercado Los Pozos").first()
        montero = db.query(Almacen).filter_by(nombre="Mercado de Montero").first()

        calzados_seed = [
            ("PAM-016-NEG-27", pampili.id, mod016.id, negro.id, sandalia.id, talla27.id, 135.0, 30),
            ("PAM-024-ROS-26", pampili.id, mod024.id, rosa.id, sandalia.id, talla26.id, 140.0, 25),
            ("MOL-2157-BLA-28", molekinha.id, mod2157.id, blanco.id, tenis.id, talla28.id, 150.0, 35),
            ("MOL-3084-NEG-29", molekinha.id, mod3084.id, negro.id, formal.id, talla29.id, 160.0, 20),
            ("KID-5120-AZU-30", kidys.id, mod5120.id, azul.id, botines.id, talla30.id, 155.0, 25),
        ]

        for cod, m_id, mod_id, c_id, tp_id, tal_id, precio, cant_central in calzados_seed:
            cal = Calzado(
                codigo=cod,
                marca_id=m_id,
                modelo_id=mod_id,
                color_id=c_id,
                tipo_calzado_id=tp_id,
                talla_id=tal_id,
                precio_mayorista=precio,
                stock_disponible=cant_central,
                activo=True
            )
            db.add(cal)
            db.flush()
            for alm in [central, barrio_lindo, ramada, pozos, montero]:
                if alm:
                    cant = cant_central if alm.id == central.id else 0
                    db.add(StockAlmacen(almacen_id=alm.id, calzado_id=cal.id, cantidad=cant))
        db.commit()


if __name__ == "__main__":
    app = create_app()
    app.run(debug=True, port=8080)
