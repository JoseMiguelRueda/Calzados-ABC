import re
import unicodedata
from flask import Blueprint, render_template, request, redirect, url_for, session, flash, current_app
from sqlalchemy.exc import IntegrityError
from database import Marca, Modelo, Color, TipoCalzado, Talla, Calzado, Almacen, StockAlmacen
from comunes import ReglaNegocioException, login_required

hu03_bp = Blueprint("hu03", __name__)


class CatalogoService:
    def __init__(self, db_session):
        self.session = db_session

    def agregarMarca(self, nombre):
        nombre_limpio = nombre.strip()
        if not nombre_limpio:
            raise ReglaNegocioException("CAT-02", "El nombre de la marca es obligatorio.")
        if self.session.query(Marca).filter(Marca.nombre.ilike(nombre_limpio)).first():
            raise ReglaNegocioException("CAT-03", f"La marca '{nombre_limpio}' ya existe.")
        marca = Marca(nombre=nombre_limpio)
        self.session.add(marca)
        self.session.commit()
        return marca

    def eliminarMarca(self, marca_id):
        marca = self.session.query(Marca).filter_by(id=int(marca_id)).first()
        if not marca:
            raise ReglaNegocioException("CAT-04", "Marca no encontrada.")
        if marca.modelos or marca.calzados:
            raise ReglaNegocioException("CAT-05", "No se puede eliminar la marca porque tiene modelos o calzados asociados.")
        self.session.delete(marca)
        self.session.commit()

    def agregarModelo(self, marca_id, nombre):
        nombre_limpio = nombre.strip()
        marca = self.session.query(Marca).filter_by(id=int(marca_id)).first()
        if not marca:
            raise ReglaNegocioException("CAT-06", "Debe seleccionar una marca válida para el modelo.")
        if not nombre_limpio:
            raise ReglaNegocioException("CAT-07", "El nombre/código del modelo es obligatorio.")
        existente = self.session.query(Modelo).filter(
            Modelo.marca_id == marca.id,
            Modelo.nombre.ilike(nombre_limpio)
        ).first()
        if existente:
            raise ReglaNegocioException("CAT-08", f"El modelo '{nombre_limpio}' ya existe para la marca {marca.nombre}.")
        modelo = Modelo(marca_id=marca.id, nombre=nombre_limpio)
        self.session.add(modelo)
        self.session.commit()
        return modelo

    def eliminarModelo(self, modelo_id):
        modelo = self.session.query(Modelo).filter_by(id=int(modelo_id)).first()
        if not modelo:
            raise ReglaNegocioException("CAT-09", "Modelo no encontrado.")
        if modelo.calzados:
            raise ReglaNegocioException("CAT-10", "No se puede eliminar el modelo porque está asignado a calzados.")
        self.session.delete(modelo)
        self.session.commit()

    def agregarColor(self, color):
        color_limpio = color.strip()
        if not color_limpio:
            raise ReglaNegocioException("CAT-11", "El nombre del color es obligatorio.")
        if self.session.query(Color).filter(Color.color.ilike(color_limpio)).first():
            raise ReglaNegocioException("CAT-12", f"El color '{color_limpio}' ya existe.")
        nuevo_color = Color(color=color_limpio)
        self.session.add(nuevo_color)
        self.session.commit()
        return nuevo_color

    def eliminarColor(self, color_id):
        color = self.session.query(Color).filter_by(id=int(color_id)).first()
        if not color:
            raise ReglaNegocioException("CAT-13", "Color no encontrado.")
        if color.calzados:
            raise ReglaNegocioException("CAT-14", "No se puede eliminar el color porque está en uso por calzados.")
        self.session.delete(color)
        self.session.commit()

    def agregarTipoCalzado(self, descripcion):
        desc_limpia = descripcion.strip()
        if not desc_limpia:
            raise ReglaNegocioException("CAT-15", "La descripción del tipo es obligatoria.")
        if self.session.query(TipoCalzado).filter(TipoCalzado.descripcion.ilike(desc_limpia)).first():
            raise ReglaNegocioException("CAT-16", f"El tipo '{desc_limpia}' ya existe.")
        tipo = TipoCalzado(descripcion=desc_limpia)
        self.session.add(tipo)
        self.session.commit()
        return tipo

    def eliminarTipoCalzado(self, tipo_id):
        tipo = self.session.query(TipoCalzado).filter_by(id=int(tipo_id)).first()
        if not tipo:
            raise ReglaNegocioException("CAT-17", "Tipo de calzado no encontrado.")
        if tipo.calzados:
            raise ReglaNegocioException("CAT-18", "No se puede eliminar el tipo porque está asignado a calzados.")
        self.session.delete(tipo)
        self.session.commit()

    def agregarTalla(self, eu, usa="", jp="", br="", cm=""):
        eu_limpio = eu.strip()
        if not eu_limpio:
            raise ReglaNegocioException("CAT-19", "La talla EU es obligatoria.")
        if self.session.query(Talla).filter_by(eu=eu_limpio, br=br.strip()).first():
            raise ReglaNegocioException("CAT-20", f"La talla EU {eu_limpio} / BR {br.strip()} ya existe.")
        talla = Talla(
            eu=eu_limpio,
            usa=usa.strip(),
            jp=jp.strip(),
            br=br.strip(),
            cm=cm.strip()
        )
        self.session.add(talla)
        self.session.commit()
        return talla

    def eliminarTalla(self, talla_id):
        talla = self.session.query(Talla).filter_by(id=int(talla_id)).first()
        if not talla:
            raise ReglaNegocioException("CAT-21", "Talla no encontrada.")
        if talla.calzados:
            raise ReglaNegocioException("CAT-22", "No se puede eliminar la talla porque está asignada a calzados.")
        self.session.delete(talla)
        self.session.commit()

    def esCombinacionDuplicada(self, marca_id, modelo_id, color_id, talla_id, excluir_id=None):
        query = self.session.query(Calzado).filter_by(
            marca_id=int(marca_id),
            modelo_id=int(modelo_id),
            color_id=int(color_id),
            talla_id=int(talla_id)
        )
        if excluir_id is not None:
            query = query.filter(Calzado.id != excluir_id)
        return query.first() is not None

    def generarCodigoCalzado(self, marca_id, modelo_id, color_id, talla_id):
        def limpiar_3(texto):
            norm = unicodedata.normalize("NFD", str(texto or "")).encode("ascii", "ignore").decode("ascii")
            solo_alnum = re.sub(r"[^A-Za-z0-9]", "", norm).upper()
            return solo_alnum[:3].ljust(3, "X")

        marca = self.session.query(Marca).filter_by(id=int(marca_id)).first()
        modelo = self.session.query(Modelo).filter_by(id=int(modelo_id)).first()
        color = self.session.query(Color).filter_by(id=int(color_id)).first()
        talla = self.session.query(Talla).filter_by(id=int(talla_id)).first()
        if not (marca and modelo and color and talla):
            raise ReglaNegocioException("CAT-26", "Atributos inválidos para generar código de calzado.")

        talla_str = re.sub(r"[^A-Za-z0-9.]", "", str(talla.eu or "")).upper()
        base_codigo = f"{limpiar_3(marca.nombre)}-{limpiar_3(modelo.nombre)}-{limpiar_3(color.color)}-{talla_str}"
        codigo_final = base_codigo
        sufijo = 2
        while self.session.query(Calzado).filter_by(codigo=codigo_final).first():
            codigo_final = f"{base_codigo}-{sufijo}"
            sufijo += 1
        return codigo_final

    def registrarCalzado(self, codigo=None, marca_id=None, modelo_id=None, color_id=None, tipo_calzado_id=None, talla_id=None,
                         precio_mayorista=120.0, stock_disponible=20):
        if self.esCombinacionDuplicada(marca_id, modelo_id, color_id, talla_id):
            raise ReglaNegocioException("E1", "Combinación Duplicada (Marca + Modelo + Color + Talla)")

        modelo = self.session.query(Modelo).filter_by(id=int(modelo_id)).first()
        if not modelo or modelo.marca_id != int(marca_id):
            raise ReglaNegocioException("E2", "El modelo seleccionado no pertenece a la marca indicada.")

        precio_val = float(precio_mayorista if precio_mayorista not in (None, "") else 120.0)
        stock_val = int(stock_disponible if stock_disponible not in (None, "") else 20)
        if precio_val <= 0:
            raise ReglaNegocioException("CAT-23", "El precio mayorista debe ser mayor a cero.")
        if stock_val < 0:
            raise ReglaNegocioException("CAT-24", "El stock disponible no puede ser negativo.")

        codigo_generado = (codigo or "").strip().upper() or self.generarCodigoCalzado(marca_id, modelo_id, color_id, talla_id)

        calzado = Calzado(
            codigo=codigo_generado,
            marca_id=int(marca_id),
            modelo_id=int(modelo_id),
            color_id=int(color_id),
            tipo_calzado_id=int(tipo_calzado_id),
            talla_id=int(talla_id),
            precio_mayorista=precio_val,
            stock_disponible=stock_val,
            activo=True
        )
        self.session.add(calzado)
        self.session.flush()

        almacenes = self.session.query(Almacen).order_by(Almacen.id).all()
        central = next((a for a in almacenes if a.es_central), almacenes[0] if almacenes else None)
        for alm in almacenes:
            cant_inicial = stock_val if (central and alm.id == central.id) else 0
            existente_st = self.session.query(StockAlmacen).filter_by(
                almacen_id=alm.id, calzado_id=calzado.id
            ).first()
            if not existente_st:
                self.session.add(StockAlmacen(
                    almacen_id=alm.id,
                    calzado_id=calzado.id,
                    cantidad=cant_inicial
                ))
        calzado.stock_disponible = stock_val if central else stock_val

        try:
            self.session.commit()
        except IntegrityError:
            self.session.rollback()
            raise ReglaNegocioException("E1", "Combinación Duplicada (Marca + Modelo + Color + Talla) o Código repetido")
        return calzado

    def darBajaLogica(self, calzado_id):
        calzado = self.session.query(Calzado).filter_by(id=calzado_id).first()
        if not calzado:
            raise ReglaNegocioException("CAT-01", "Calzado no encontrado")
        calzado.activo = False
        self.session.commit()
        return calzado

    def eliminarCalzado(self, calzado_id):
        calzado = self.session.query(Calzado).filter_by(id=int(calzado_id)).first()
        if not calzado:
            raise ReglaNegocioException("CAT-01", "Calzado no encontrado")
        if calzado.detalles_pedido:
            raise ReglaNegocioException("CAT-25", "No se puede eliminar un calzado que ya forma parte de pedidos.")
        self.session.delete(calzado)
        self.session.commit()


@hu03_bp.route("/catalogo", methods=["GET", "POST"])
@login_required(roles=["Administrador", "Cliente Mayorista"])
def catalogo():
    db = current_app.config["DB_SESSION"]
    catalogo_srv = CatalogoService(db)
    if request.method == "POST":
        if session.get("rol") != "Administrador":
            flash("Solo el Administrador puede modificar el catálogo.", "danger")
            return redirect(url_for("hu03.catalogo"))
        accion = request.form.get("accion")
        try:
            if accion == "crear":
                catalogo_srv.registrarCalzado(
                    codigo=request.form.get("codigo", ""),
                    marca_id=request.form.get("marca_id"),
                    modelo_id=request.form.get("modelo_id"),
                    color_id=request.form.get("color_id"),
                    tipo_calzado_id=request.form.get("tipo_calzado_id"),
                    talla_id=request.form.get("talla_id"),
                    precio_mayorista=request.form.get("precio_mayorista", 120.0),
                    stock_disponible=request.form.get("stock_disponible", 20)
                )
                flash("Calzado registrado en catálogo como Activo.", "success")
            elif accion == "baja":
                catalogo_srv.darBajaLogica(int(request.form.get("calzado_id")))
                flash("Calzado dado de baja lógica (Inactivo).", "warning")
            elif accion == "eliminar":
                catalogo_srv.eliminarCalzado(int(request.form.get("calzado_id")))
                flash("Calzado eliminado del catálogo.", "warning")

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
        return redirect(url_for("hu03.catalogo"))

    return render_template(
        "catalogo.html",
        marcas=db.query(Marca).order_by(Marca.nombre).all(),
        modelos=db.query(Modelo).order_by(Modelo.marca_id, Modelo.nombre).all(),
        colores=db.query(Color).order_by(Color.color).all(),
        tipos=db.query(TipoCalzado).order_by(TipoCalzado.descripcion).all(),
        tallas=db.query(Talla).order_by(Talla.eu).all(),
        calzados=db.query(Calzado).all()
    )
