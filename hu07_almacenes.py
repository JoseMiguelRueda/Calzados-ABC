from datetime import datetime, date
from flask import Blueprint, render_template, request, redirect, url_for, flash, current_app
from database import Almacen, StockAlmacen, Calzado, ImportacionFabrica, TraspasoAlmacen
from comunes import ReglaNegocioException, login_required

hu07_bp = Blueprint("hu07", __name__)


class AlmacenService:
    def __init__(self, db_session):
        self.session = db_session

    def _obtener_o_crear_stock(self, almacen_id, calzado_id):
        st = self.session.query(StockAlmacen).filter_by(
            almacen_id=int(almacen_id),
            calzado_id=int(calzado_id)
        ).first()
        if not st:
            st = StockAlmacen(almacen_id=int(almacen_id), calzado_id=int(calzado_id), cantidad=0)
            self.session.add(st)
            self.session.flush()
        return st

    def _recalcular_stock_global_calzado(self, calzado_id):
        calzado = self.session.query(Calzado).filter_by(id=int(calzado_id)).first()
        if calzado:
            total_almacenes = sum(
                s.cantidad for s in self.session.query(StockAlmacen).filter_by(calzado_id=calzado.id).all()
            )
            calzado.stock_disponible = total_almacenes

    def registrarImportacionFabrica(self, codigo_lote, fabrica, calzado_id, cantidad, fecha_arribo=None):
        """HU-07: Registra importación de fábrica directamente al Almacén Central."""
        cant = int(cantidad)
        if cant <= 0:
            raise ReglaNegocioException("IMP-01", "La cantidad importada debe ser mayor a cero.")
        if not codigo_lote or not codigo_lote.strip():
            raise ReglaNegocioException("IMP-02", "El código de lote es obligatorio.")
        if not fabrica or not fabrica.strip():
            raise ReglaNegocioException("IMP-03", "El nombre de la fábrica es obligatorio.")

        calzado = self.session.query(Calzado).filter_by(id=int(calzado_id)).first()
        if not calzado:
            raise ReglaNegocioException("IMP-04", "Calzado no encontrado.")

        central = self.session.query(Almacen).filter_by(es_central=True).first()
        if not central:
            raise ReglaNegocioException("IMP-05", "No existe Almacén Central configurado.")

        imp = ImportacionFabrica(
            codigo_lote=codigo_lote.strip(),
            fabrica=fabrica.strip(),
            calzado_id=calzado.id,
            almacen_id=central.id,
            cantidad=cant,
            fecha_arribo=fecha_arribo or date.today()
        )
        self.session.add(imp)

        st_central = self._obtener_o_crear_stock(central.id, calzado.id)
        st_central.cantidad += cant
        self._recalcular_stock_global_calzado(calzado.id)

        self.session.commit()
        return imp

    def realizarTraspaso(self, almacen_origen_id, almacen_destino_id, calzado_id, cantidad):
        """HU-08 (RN-04): Transacción atómica de traspaso inter-almacén con actualización simultánea de stock."""
        origen_id = int(almacen_origen_id)
        destino_id = int(almacen_destino_id)
        cal_id = int(calzado_id)
        cant = int(cantidad)

        if origen_id == destino_id:
            raise ReglaNegocioException("RN-04", "El almacén de origen y destino no pueden ser el mismo.")
        if cant <= 0:
            raise ReglaNegocioException("TRP-01", "La cantidad a traspasar debe ser mayor a cero.")

        origen = self.session.query(Almacen).filter_by(id=origen_id).first()
        destino = self.session.query(Almacen).filter_by(id=destino_id).first()
        if not origen or not destino:
            raise ReglaNegocioException("TRP-02", "Almacén de origen o destino no encontrado.")

        st_origen = self._obtener_o_crear_stock(origen_id, cal_id)
        if st_origen.cantidad < cant:
            raise ReglaNegocioException(
                "RN-04",
                f"Stock insuficiente en {origen.nombre} (Disponible: {st_origen.cantidad}, Solicitado: {cant})."
            )

        st_destino = self._obtener_o_crear_stock(destino_id, cal_id)

        try:
            st_origen.cantidad -= cant
            st_destino.cantidad += cant

            traspaso = TraspasoAlmacen(
                codigo_traspaso=f"TRP-{datetime.utcnow().strftime('%Y%m%d%H%M%S%f')[-10:]}",
                almacen_origen_id=origen_id,
                almacen_destino_id=destino_id,
                calzado_id=cal_id,
                cantidad=cant
            )
            self.session.add(traspaso)
            self._recalcular_stock_global_calzado(cal_id)
            self.session.commit()
            return traspaso
        except Exception:
            self.session.rollback()
            raise


@hu07_bp.route("/almacenes", methods=["GET", "POST"])
@login_required(roles=["Administrador", "Encargado de Pedidos"])
def almacenes():
    db = current_app.config["DB_SESSION"]
    alm_srv = AlmacenService(db)

    if request.method == "POST":
        accion = request.form.get("accion")
        try:
            if accion == "importar":
                fecha_str = request.form.get("fecha_arribo")
                fecha_obj = date.fromisoformat(fecha_str) if fecha_str else date.today()
                imp = alm_srv.registrarImportacionFabrica(
                    codigo_lote=request.form.get("codigo_lote", ""),
                    fabrica=request.form.get("fabrica", ""),
                    calzado_id=request.form.get("calzado_id"),
                    cantidad=request.form.get("cantidad"),
                    fecha_arribo=fecha_obj
                )
                flash(f"Importación {imp.codigo_lote} ingresada a Almacén Central (+{imp.cantidad} uds).", "success")

            elif accion == "traspaso":
                trp = alm_srv.realizarTraspaso(
                    almacen_origen_id=request.form.get("almacen_origen_id"),
                    almacen_destino_id=request.form.get("almacen_destino_id"),
                    calzado_id=request.form.get("calzado_id"),
                    cantidad=request.form.get("cantidad")
                )
                flash(f"Traspaso {trp.codigo_traspaso} completado ({trp.cantidad} uds).", "success")

        except ReglaNegocioException as e:
            db.rollback()
            flash(str(e), "danger")
        except Exception as e:
            db.rollback()
            flash(f"Error en almacenes: {str(e)}", "danger")
        return redirect(url_for("hu07.almacenes"))

    return render_template(
        "almacenes.html",
        almacenes=db.query(Almacen).order_by(Almacen.id).all(),
        stocks=db.query(StockAlmacen).all(),
        calzados=db.query(Calzado).all(),
        importaciones=db.query(ImportacionFabrica).order_by(ImportacionFabrica.id.desc()).all(),
        traspasos=db.query(TraspasoAlmacen).order_by(TraspasoAlmacen.id.desc()).all()
    )
