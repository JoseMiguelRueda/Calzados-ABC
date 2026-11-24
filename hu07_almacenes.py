from datetime import datetime, date
from flask import Blueprint, render_template, request, redirect, url_for, session, flash, current_app
from sqlalchemy import inspect, text
from database import Almacen, StockAlmacen, Calzado, ImportacionFabrica, TraspasoAlmacen
from comunes import ReglaNegocioException, login_required

hu07_bp = Blueprint("hu07", __name__)


def _asegurar_esquema_almacenes(db_session):
    try:
        from database import _migrar_columnas_faltantes
        _migrar_columnas_faltantes(db_session.get_bind())
    except Exception:
        db_session.rollback()


class AlmacenService:
    def __init__(self, db_session):
        self.session = db_session
        _asegurar_esquema_almacenes(self.session)

    def _sincronizarTotalCalzado(self, calzado):
        if not calzado:
            return
        total = sum(
            int(s.cantidad or 0)
            for s in self.session.query(StockAlmacen).filter_by(calzado_id=calzado.id).all()
        )
        calzado.stock_disponible = total

    def registrarImportacion(self, codigo_lote, fabrica_origen, almacen_id, calzado_id, cantidad, fecha_arribo=None):
        lote_limpio = (codigo_lote or "").strip()
        fabrica_limpia = (fabrica_origen or "").strip()
        if not lote_limpio or not fabrica_limpia:
            raise ReglaNegocioException("IMP-01", "Debe completar el código de lote y la fábrica de origen.")

        try:
            cant_val = int(cantidad)
        except (TypeError, ValueError):
            raise ReglaNegocioException("IMP-02", "La cantidad debe ser un número entero.")
        if cant_val <= 0:
            raise ReglaNegocioException("IMP-03", "La cantidad a ingresar debe ser mayor a cero.")

        almacen = self.session.query(Almacen).filter_by(id=int(almacen_id)).first()
        if not almacen:
            raise ReglaNegocioException("IMP-04", "Almacén de destino no encontrado.")
        if not getattr(almacen, "activo", True):
            raise ReglaNegocioException("IMP-05", "El almacén seleccionado está inactivo.")

        calzado = self.session.query(Calzado).filter_by(id=int(calzado_id)).first()
        if not calzado:
            raise ReglaNegocioException("IMP-06", "Calzado no encontrado.")

        if self.session.query(ImportacionFabrica).filter(ImportacionFabrica.codigo_lote.ilike(lote_limpio)).first():
            raise ReglaNegocioException("IMP-07", f"El lote '{lote_limpio}' ya fue registrado.")

        fecha_val = date.today()
        if fecha_arribo:
            try:
                fecha_val = datetime.strptime(str(fecha_arribo).strip(), "%Y-%m-%d").date()
            except ValueError:
                pass

        st = self.session.query(StockAlmacen).filter_by(
            almacen_id=almacen.id, calzado_id=calzado.id
        ).first()
        if not st:
            st = StockAlmacen(almacen_id=almacen.id, calzado_id=calzado.id, cantidad=0)
            self.session.add(st)
            self.session.flush()

        st.cantidad = int(st.cantidad or 0) + cant_val
        self._sincronizarTotalCalzado(calzado)

        imp = ImportacionFabrica(
            codigo_lote=lote_limpio,
            fabrica_origen=fabrica_limpia,
            almacen_id=almacen.id,
            calzado_id=calzado.id,
            cantidad=cant_val,
            fecha_arribo=fecha_val
        )
        self.session.add(imp)
        self.session.commit()
        return imp

    def registrarTraspaso(self, almacen_origen_id, almacen_destino_id, calzado_id, cantidad):
        if int(almacen_origen_id) == int(almacen_destino_id):
            raise ReglaNegocioException("E2", "Almacén Duplicado: origen y destino deben ser distintos.")

        try:
            cant_val = int(cantidad)
        except (TypeError, ValueError):
            raise ReglaNegocioException("TRP-01", "La cantidad a traspasar debe ser un número entero.")
        if cant_val <= 0:
            raise ReglaNegocioException("TRP-02", "La cantidad a traspasar debe ser mayor a cero.")

        origen = self.session.query(Almacen).filter_by(id=int(almacen_origen_id)).first()
        destino = self.session.query(Almacen).filter_by(id=int(almacen_destino_id)).first()
        if not origen or not destino:
            raise ReglaNegocioException("TRP-03", "Almacén de origen o destino no encontrado.")
        if not getattr(origen, "activo", True) or not getattr(destino, "activo", True):
            raise ReglaNegocioException("TRP-04", "Uno de los almacenes seleccionados está inactivo.")

        calzado = self.session.query(Calzado).filter_by(id=int(calzado_id)).first()
        if not calzado:
            raise ReglaNegocioException("TRP-05", "Calzado no encontrado.")

        st_origen = self.session.query(StockAlmacen).filter_by(
            almacen_id=origen.id, calzado_id=calzado.id
        ).first()
        disp_origen = int(st_origen.cantidad or 0) if st_origen else 0
        if disp_origen < cant_val:
            raise ReglaNegocioException("E1", "Stock Insuficiente en Origen")

        st_destino = self.session.query(StockAlmacen).filter_by(
            almacen_id=destino.id, calzado_id=calzado.id
        ).first()
        if not st_destino:
            st_destino = StockAlmacen(almacen_id=destino.id, calzado_id=calzado.id, cantidad=0)
            self.session.add(st_destino)
            self.session.flush()

        st_origen.cantidad = disp_origen - cant_val
        st_destino.cantidad = int(st_destino.cantidad or 0) + cant_val
        self._sincronizarTotalCalzado(calzado)

        traspaso = TraspasoAlmacen(
            codigo_traspaso=f"TRP-{datetime.utcnow().strftime('%Y%m%d%H%M%S%f')[-10:]}",
            almacen_origen_id=origen.id,
            almacen_destino_id=destino.id,
            calzado_id=calzado.id,
            cantidad=cant_val
        )
        self.session.add(traspaso)
        self.session.commit()
        return traspaso


@hu07_bp.route("/almacenes", methods=["GET", "POST"])
@login_required(roles=["Administrador", "Encargado de Almacén", "Encargado de Pedidos"])
def almacenes():
    db = current_app.config["DB_SESSION"]
    srv = AlmacenService(db)
    try:
        if request.method == "POST":
            if session.get("rol") not in ("Administrador", "Encargado de Almacén"):
                flash("Solo el Administrador o Encargado de Almacén puede operar en almacenes.", "danger")
                return redirect(url_for("hu07.almacenes"))

            accion = request.form.get("accion")
            try:
                if accion == "importar":
                    imp = srv.registrarImportacion(
                        codigo_lote=request.form.get("codigo_lote", ""),
                        fabrica_origen=request.form.get("fabrica_origen", ""),
                        almacen_id=request.form.get("almacen_id") or (
                            db.query(Almacen).filter_by(es_central=True).first().id
                            if db.query(Almacen).filter_by(es_central=True).first()
                            else db.query(Almacen).first().id
                        ),
                        calzado_id=request.form.get("calzado_id"),
                        cantidad=request.form.get("cantidad"),
                        fecha_arribo=request.form.get("fecha_arribo")
                    )
                    flash(f"Importación {imp.codigo_lote} (+{imp.cantidad}) registrada.", "success")
                elif accion == "traspasar":
                    trp = srv.registrarTraspaso(
                        almacen_origen_id=request.form.get("almacen_origen_id"),
                        almacen_destino_id=request.form.get("almacen_destino_id"),
                        calzado_id=request.form.get("calzado_id"),
                        cantidad=request.form.get("cantidad")
                    )
                    flash(f"Traspaso {trp.codigo_traspaso} ({trp.cantidad} uds) ejecutado.", "success")
            except ReglaNegocioException as e:
                db.rollback()
                flash(str(e), "danger")
            except Exception as e:
                db.rollback()
                flash(f"Error en almacenes: {str(e)}", "danger")
            return redirect(url_for("hu07.almacenes"))

        buscar_modelo = request.args.get("modelo", "").strip().lower()
        lista_almacenes = db.query(Almacen).order_by(Almacen.id).all()
        lista_calzados = db.query(Calzado).order_by(Calzado.codigo).all()
        lista_stocks = db.query(StockAlmacen).all()
        importaciones = db.query(ImportacionFabrica).order_by(ImportacionFabrica.id.desc()).all()
        traspasos = db.query(TraspasoAlmacen).order_by(TraspasoAlmacen.id.desc()).all()

        if buscar_modelo:
            lista_stocks = [
                s for s in lista_stocks
                if s.calzado and (
                    buscar_modelo in (s.calzado.modelo.nombre or "").lower()
                    or buscar_modelo in (s.calzado.codigo or "").lower()
                    or buscar_modelo in (s.calzado.marca.nombre or "").lower()
                )
            ]

        return render_template(
            "almacenes.html",
            almacenes=lista_almacenes,
            calzados=lista_calzados,
            stocks=lista_stocks,
            importaciones=importaciones,
            traspasos=traspasos,
            buscar_modelo=buscar_modelo
        )
    except Exception as e:
        db.rollback()
        flash(f"Error al cargar vista de almacenes: {str(e)}", "danger")
        return render_template(
            "almacenes.html",
            almacenes=[],
            calzados=[],
            stocks=[],
            importaciones=[],
            traspasos=[],
            buscar_modelo=""
        )
    finally:
        db.remove()
