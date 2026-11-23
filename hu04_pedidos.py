import time
from datetime import datetime, date
from flask import Blueprint, render_template, request, redirect, url_for, session, flash, current_app
from database import Pedido, DetallePedido, Calzado, Cliente, Almacen, StockAlmacen
from comunes import ReglaNegocioException, login_required
from hu02_clientes import ClienteService

hu04_bp = Blueprint("hu04", __name__)


class PedidoService:
    def __init__(self, db_session):
        self.session = db_session
        self.cliente_srv = ClienteService(db_session)

    def _parsearFecha(self, fecha_estimada):
        if fecha_estimada is None or fecha_estimada == "":
            return None
        if isinstance(fecha_estimada, date) and not isinstance(fecha_estimada, datetime):
            return fecha_estimada
        if isinstance(fecha_estimada, datetime):
            return fecha_estimada.date()
        if isinstance(fecha_estimada, str):
            return date.fromisoformat(fecha_estimada.strip())
        raise ReglaNegocioException("PED-09", "Formato de fecha estimada no válido.")

    def _resolverAlmacen(self, nombre_almacen=None):
        if nombre_almacen:
            alm = self.session.query(Almacen).filter(Almacen.nombre.ilike(nombre_almacen.strip())).first()
            if alm:
                return alm
        alm = self.session.query(Almacen).filter_by(es_central=True).first()
        if not alm:
            alm = self.session.query(Almacen).order_by(Almacen.id).first()
        if not alm:
            raise ReglaNegocioException("ALM-01", "No hay almacenes registrados en el sistema.")
        return alm

    def _obtenerStockAlmacen(self, almacen_id, calzado_id, crear_si_no_existe=True):
        st = self.session.query(StockAlmacen).filter_by(
            almacen_id=int(almacen_id),
            calzado_id=int(calzado_id)
        ).first()
        if not st and crear_si_no_existe:
            st = StockAlmacen(almacen_id=int(almacen_id), calzado_id=int(calzado_id), cantidad=0)
            self.session.add(st)
            self.session.flush()
        return st

    def _sincronizarStockTotalCalzado(self, calzado):
        if not calzado:
            return
        total = sum(
            int(s.cantidad or 0)
            for s in self.session.query(StockAlmacen).filter_by(calzado_id=calzado.id).all()
        )
        calzado.stock_disponible = total

    def actualizarFechaEstimada(self, pedido_id, fecha_estimada):
        """Permite establecer o modificar manualmente la fecha estimada en cualquier momento."""
        pedido = self.session.query(Pedido).filter_by(id=int(pedido_id)).first()
        if not pedido:
            raise ReglaNegocioException("PED-05", "Pedido no encontrado.")
        try:
            pedido.fecha_estimada_entrega = self._parsearFecha(fecha_estimada)
            self.session.commit()
            return pedido
        except ReglaNegocioException:
            self.session.rollback()
            raise
        except Exception:
            self.session.rollback()
            raise ReglaNegocioException("PED-09", "La fecha estimada ingresada no es válida.")

    def crearPedido(self, cliente_id, items, observacion="", permitir_faltante=True, fecha_estimada=None):
        """HU-04 (RN-03, RNF-01): Recibe pedido en estado Pendiente en < 3s con fecha estimada manual."""
        t_inicio = time.perf_counter()
        self.cliente_srv.validarPermisoPedido(int(cliente_id))

        if not items:
            raise ReglaNegocioException("PED-01", "Debe agregar al menos un calzado al pedido.")

        fecha_manual = self._parsearFecha(fecha_estimada)
        almacen = self._resolverAlmacen(observacion)

        cantidades_por_calzado = {}
        for item in items:
            calzado_id = int(item["calzado_id"])
            cantidad = int(item["cantidad"])
            if cantidad <= 0:
                raise ReglaNegocioException("PED-02", "La cantidad por ítem debe ser mayor a cero.")
            cantidades_por_calzado[calzado_id] = cantidades_por_calzado.get(calzado_id, 0) + cantidad

        pedido = Pedido(
            codigo_pedido=f"PED-{datetime.utcnow().strftime('%Y%m%d%H%M%S%f')[-10:]}",
            cliente_id=int(cliente_id),
            estado="Pendiente",
            observacion=almacen.nombre,
            fecha_estimada_entrega=fecha_manual
        )
        self.session.add(pedido)
        self.session.flush()

        total_pedido = 0.0

        for calzado_id, cantidad in cantidades_por_calzado.items():
            calzado = self.session.query(Calzado).filter_by(id=calzado_id).first()
            if not calzado or not calzado.activo:
                raise ReglaNegocioException("PED-03", f"Calzado ID {calzado_id} no disponible o inactivo.")

            st_alm = self._obtenerStockAlmacen(almacen.id, calzado.id, crear_si_no_existe=True)
            disponible_alm = max(0, int(st_alm.cantidad or 0))
            if disponible_alm < cantidad and not permitir_faltante:
                raise ReglaNegocioException(
                    "PED-04",
                    f"Stock insuficiente en {almacen.nombre} para {calzado.codigo} (Disponible: {disponible_alm}, Solicitado: {cantidad})."
                )

            faltante = max(0, cantidad - disponible_alm)
            reservable = cantidad - faltante

            precio = float(calzado.precio_mayorista or 0.0)
            subtotal = round(precio * cantidad, 2)
            detalle = DetallePedido(
                pedido_id=pedido.id,
                calzado_id=calzado.id,
                cantidad=cantidad,
                cantidad_reservada=reservable,
                cantidad_faltante=faltante,
                precio_unitario=precio,
                subtotal=subtotal
            )
            self.session.add(detalle)
            total_pedido += subtotal

        pedido.total = round(total_pedido, 2)
        self.session.commit()

        elapsed = time.perf_counter() - t_inicio
        if elapsed >= 3.0:
            raise ReglaNegocioException("RNF-01", f"Tiempo de procesamiento excedió 3s ({elapsed:.2f}s).")

        return pedido

    def reservarStockPedido(self, pedido_id):
        """HU-05: Valida y descuenta del stock del almacén correspondiente al reservar."""
        pedido = self.session.query(Pedido).filter_by(id=int(pedido_id)).first()
        if not pedido:
            raise ReglaNegocioException("PED-05", "Pedido no encontrado.")
        if pedido.estado == "Reservado":
            raise ReglaNegocioException("PED-08", "El pedido ya se encuentra Reservado.")
        if pedido.estado != "Pendiente":
            raise ReglaNegocioException("PED-08", f"No se puede reservar un pedido en estado {pedido.estado}.")

        self.cliente_srv.validarPermisoPedido(pedido.cliente_id)
        almacen = self._resolverAlmacen(pedido.observacion)

        faltante_total = 0
        try:
            for det in pedido.detalles:
                calzado = det.calzado
                if not calzado or not calzado.activo:
                    raise ReglaNegocioException("PED-03", "Calzado inactivo o inexistente.")

                st_alm = self._obtenerStockAlmacen(almacen.id, calzado.id, crear_si_no_existe=True)
                disp_alm = int(st_alm.cantidad or 0)
                res_cal = int(calzado.stock_reservado or 0)
                solicitado = int(det.cantidad)

                if disp_alm < solicitado:
                    faltante = solicitado - disp_alm
                    det.cantidad_reservada = 0
                    det.cantidad_faltante = faltante
                    faltante_total += faltante
                else:
                    st_alm.cantidad = disp_alm - solicitado
                    calzado.stock_reservado = res_cal + solicitado
                    det.cantidad_reservada = solicitado
                    det.cantidad_faltante = 0
                    self._sincronizarStockTotalCalzado(calzado)

            if faltante_total > 0:
                self.session.commit()
                raise ReglaNegocioException(
                    "PED-04",
                    f"Stock insuficiente en {almacen.nombre} para reservar (Faltan {faltante_total} uds)."
                )

            pedido.estado = "Reservado"
            self.session.commit()
            return pedido
        except Exception:
            self.session.rollback()
            raise

    def confirmarPedido(self, pedido_id, forzar_con_faltante=False):
        """HU-05: Valida stock en el almacén correspondiente y confirma comercialmente."""
        pedido = self.session.query(Pedido).filter_by(id=int(pedido_id)).first()
        if not pedido:
            raise ReglaNegocioException("PED-05", "Pedido no encontrado.")
        if pedido.estado not in ("Pendiente", "Reservado"):
            raise ReglaNegocioException("PED-06", f"Solo se pueden confirmar pedidos Pendiente o Reservado (actual: {pedido.estado}).")

        self.cliente_srv.validarPermisoPedido(pedido.cliente_id)
        almacen = self._resolverAlmacen(pedido.observacion)

        faltante_pendiente = 0
        try:
            for det in pedido.detalles:
                calzado = det.calzado
                if not calzado or not calzado.activo:
                    raise ReglaNegocioException("PED-03", "Calzado inactivo o inexistente.")

                st_alm = self._obtenerStockAlmacen(almacen.id, calzado.id, crear_si_no_existe=True)
                disp_alm = int(st_alm.cantidad or 0)
                res_cal = int(calzado.stock_reservado or 0)
                det_res = int(det.cantidad_reservada or 0)
                solicitado = int(det.cantidad)

                if det_res >= solicitado:
                    res_cal = max(0, res_cal - solicitado)
                    det.cantidad_reservada = solicitado
                    det.cantidad_faltante = 0
                else:
                    faltante_calc = max(0, solicitado - disp_alm)
                    if faltante_calc > 0 and not forzar_con_faltante:
                        raise ReglaNegocioException(
                            "PED-04",
                            f"Stock insuficiente en {almacen.nombre} para {calzado.codigo} (Disponible: {disp_alm}, Solicitado: {solicitado}, Faltan: {faltante_calc})."
                        )
                    if faltante_calc > 0 and forzar_con_faltante:
                        det.cantidad_reservada = 0
                        det.cantidad_faltante = faltante_calc
                        faltante_pendiente += faltante_calc
                    else:
                        disp_alm -= solicitado
                        det.cantidad_reservada = solicitado
                        det.cantidad_faltante = 0

                st_alm.cantidad = disp_alm
                calzado.stock_reservado = res_cal
                self._sincronizarStockTotalCalzado(calzado)

            pedido.estado = "Confirmado"
            self.session.commit()
            return pedido
        except Exception:
            self.session.rollback()
            raise

    def anularPedido(self, pedido_id):
        """Devuelve el stock reservado al stock del almacén correspondiente y sincroniza el catálogo."""
        pedido = self.session.query(Pedido).filter_by(id=int(pedido_id)).first()
        if not pedido:
            raise ReglaNegocioException("PED-05", "Pedido no encontrado.")
        if pedido.estado == "Anulado":
            raise ReglaNegocioException("PED-07", "El pedido ya se encuentra anulado.")

        almacen = self._resolverAlmacen(pedido.observacion)

        try:
            for det in pedido.detalles:
                calzado = det.calzado
                det_res = int(det.cantidad_reservada or 0)
                if calzado and det_res > 0:
                    st_alm = self._obtenerStockAlmacen(almacen.id, calzado.id, crear_si_no_existe=True)
                    if pedido.estado == "Reservado":
                        calzado.stock_reservado = max(0, int(calzado.stock_reservado or 0) - det_res)
                        st_alm.cantidad = int(st_alm.cantidad or 0) + det_res
                    elif pedido.estado == "Confirmado":
                        st_alm.cantidad = int(st_alm.cantidad or 0) + det_res
                    det.cantidad_reservada = 0
                    self._sincronizarStockTotalCalzado(calzado)

            pedido.estado = "Anulado"
            self.session.commit()
            return pedido
        except Exception:
            self.session.rollback()
            raise


@hu04_bp.route("/pedidos", methods=["GET", "POST"])
@login_required(roles=["Administrador", "Encargado de Pedidos", "Cliente Mayorista"])
def pedidos():
    db = current_app.config["DB_SESSION"]
    pedido_srv = PedidoService(db)
    rol = session.get("rol")
    user_id = session.get("user_id")
    es_gestor = rol in ("Administrador", "Encargado de Pedidos")

    if request.method == "POST":
        accion = request.form.get("accion")
        try:
            if accion == "crear":
                cliente_id = int(request.form.get("cliente_id")) if es_gestor else int(user_id)
                calzado_id = request.form.get("calzado_id")
                cantidad = request.form.get("cantidad")
                observacion = request.form.get("observacion", "")
                fecha_estimada = request.form.get("fecha_estimada_entrega", "")

                items = []
                if calzado_id and cantidad:
                    items.append({"calzado_id": calzado_id, "cantidad": cantidad})

                ped = pedido_srv.crearPedido(
                    cliente_id=cliente_id,
                    items=items,
                    observacion=observacion,
                    permitir_faltante=True,
                    fecha_estimada=fecha_estimada
                )
                total_falt = sum(int(d.cantidad_faltante or 0) for d in ped.detalles)
                if total_falt > 0:
                    flash(
                        f"Pedido {ped.codigo_pedido} registrado en Pendiente. Faltan {total_falt} uds en {ped.observacion}.",
                        "warning"
                    )
                else:
                    flash(f"Pedido {ped.codigo_pedido} registrado en estado Pendiente.", "success")

            elif accion == "actualizar_fecha":
                pedido_id = int(request.form.get("pedido_id"))
                pedido_obj = db.query(Pedido).filter_by(id=pedido_id).first()
                if not es_gestor and (not pedido_obj or pedido_obj.cliente_id != user_id):
                    flash("No puede modificar pedidos de otro cliente.", "danger")
                    return redirect(url_for("hu04.pedidos"))
                ped = pedido_srv.actualizarFechaEstimada(
                    pedido_id=pedido_id,
                    fecha_estimada=request.form.get("fecha_estimada_entrega", "")
                )
                flash(
                    f"Fecha estimada de {ped.codigo_pedido} actualizada a {ped.fecha_estimada_entrega or 'sin definir'}.",
                    "success"
                )

            elif accion == "reservar" and es_gestor:
                ped = pedido_srv.reservarStockPedido(int(request.form.get("pedido_id")))
                flash(f"Stock descontado en {ped.observacion} y reservado para {ped.codigo_pedido}.", "info")

            elif accion == "confirmar" and es_gestor:
                forzar = (request.form.get("forzar_faltante") == "on")
                ped = pedido_srv.confirmarPedido(int(request.form.get("pedido_id")), forzar_con_faltante=forzar)
                flash(f"Pedido {ped.codigo_pedido} confirmado comercialmente.", "success")

            elif accion == "anular":
                pedido_id = int(request.form.get("pedido_id"))
                pedido_obj = db.query(Pedido).filter_by(id=pedido_id).first()
                if not es_gestor and (not pedido_obj or pedido_obj.cliente_id != user_id):
                    flash("No puede anular pedidos de otro cliente.", "danger")
                    return redirect(url_for("hu04.pedidos"))
                pedido_srv.anularPedido(pedido_id)
                flash("Pedido anulado y stock devuelto al almacén.", "warning")

        except ReglaNegocioException as e:
            db.rollback()
            flash(str(e), "danger")
        except Exception as e:
            db.rollback()
            flash(f"Error al procesar pedido: {str(e)}", "danger")
        finally:
            db.remove()
        return redirect(url_for("hu04.pedidos"))

    try:
        if es_gestor:
            lista_pedidos = db.query(Pedido).order_by(Pedido.id.desc()).all()
        else:
            lista_pedidos = db.query(Pedido).filter_by(cliente_id=user_id).order_by(Pedido.id.desc()).all()

        return render_template(
            "pedidos.html",
            pedidos=lista_pedidos,
            clientes=db.query(Cliente).all(),
            calzados_activos=db.query(Calzado).filter_by(activo=True).all(),
            almacenes=db.query(Almacen).order_by(Almacen.id).all(),
            stocks_almacen=db.query(StockAlmacen).all(),
            es_gestor=es_gestor
        )
    finally:
        db.remove()
