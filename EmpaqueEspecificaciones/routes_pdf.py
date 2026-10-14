# routes_pdf.py
from flask import (
    Blueprint, render_template, request, session,
    abort, send_file, redirect, url_for, flash,
    send_from_directory,
)
from functools import wraps
from datetime import datetime
from pathlib import Path
import json
import uuid as uuid_lib

from werkzeug.utils import secure_filename

from db import get_db_connection
from permisos import login_required
from pdf_utils import generar_pdf
import storage


# ─────────────────────────────────────────────
# Configuración de uploads
# ─────────────────────────────────────────────
UPLOADS_DIR = Path(__file__).parent / "uploads"
UPLOADS_DIR.mkdir(exist_ok=True)

EXTENSIONES_PERMITIDAS = {'.png', '.jpg', '.jpeg', '.gif', '.webp', '.bmp'}


# ─────────────────────────────────────────────
# Blueprint
# ─────────────────────────────────────────────
pdf_bp = Blueprint(
    "pdf_generator",
    __name__,
    template_folder="templates",
)


TIPOS = {
    "diseno_grafico":   {"nombre": "Diseño Gráfico",      "icono": "fas fa-drafting-compass", "color": "primary"},
    "material_empaque": {"nombre": "Material de Empaque", "icono": "fas fa-box",              "color": "success"},
    "etiqueta":         {"nombre": "Etiqueta",            "icono": "fas fa-tag",              "color": "warning"},
    "etiqueta_zebra":   {"nombre": "Etiqueta Zebra",      "icono": "fas fa-barcode",          "color": "danger"},
}


def _template_formulario(tipo: str) -> str:
    """Devuelve el template del formulario según el tipo."""
    templates = {
        'material_empaque': 'formulario_material_empaque.html',
        # 'etiqueta':         'formulario_etiqueta.html',
        # 'etiqueta_zebra':   'formulario_etiqueta_zebra.html',
    }
    return templates.get(tipo, 'formulario.html')


def _contexto_base():
    return {
        "tipos": TIPOS,
        "usuario": session.get("username", ""),
        "es_admin": session.get("es_admin", False),
    }


# ─────────────────────────────────────────────
# Listado de usuarios (para admin)
# ─────────────────────────────────────────────
@pdf_bp.route("/usuarios")
@login_required
def usuarios():
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT id, nombre, activo, es_admin, fecha_alta FROM usuarios ORDER BY id")
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    return render_template("usuarios.html", usuarios=rows, **_contexto_base())


@pdf_bp.route("/usuarios/crear", methods=["POST"])
@login_required
def crear_usuario():
    from werkzeug.security import generate_password_hash
    data = request.get_json() or {}
    nombre   = data.get("nombre", "").strip()
    password = data.get("password", "")
    es_admin = bool(data.get("es_admin", False))

    if not nombre or not password:
        return {"success": False, "error": "Complete todos los campos"}
    if len(password) < 4:
        return {"success": False, "error": "Mínimo 4 caracteres"}

    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT id FROM usuarios WHERE nombre = ?", (nombre,))
    if cur.fetchone():
        conn.close()
        return {"success": False, "error": "El usuario ya existe"}

    cur.execute("""
        INSERT INTO usuarios (nombre, password_hash, activo, es_admin)
        VALUES (?, ?, 1, ?)
    """, (nombre, generate_password_hash(password), 1 if es_admin else 0))
    conn.commit()
    conn.close()
    return {"success": True, "mensaje": f"Usuario {nombre} creado"}


# ─────────────────────────────────────────────
# Panel
# ─────────────────────────────────────────────
@pdf_bp.route("/especificaciones-pdf")
@pdf_bp.route("/especificaciones-pdf/")
@login_required
def panel():
    ultimas = storage.ultimas_generadas(limite=15)
    return render_template("panel.html", ultimas=ultimas, **_contexto_base())


# ─────────────────────────────────────────────
# Formulario
# ─────────────────────────────────────────────
@pdf_bp.route("/especificaciones-pdf/tipo/<tipo>")
@login_required
def formulario(tipo):
    if tipo not in TIPOS:
        abort(404)
    return render_template(
        _template_formulario(tipo),
        tipo=tipo, tipo_info=TIPOS[tipo],
        prefill=None,
        original=None,
        origen_id=None,
        **_contexto_base(),
    )


# ─────────────────────────────────────────────
# Nueva versión (precarga desde existente)
# ─────────────────────────────────────────────
@pdf_bp.route("/especificaciones-pdf/nueva-version/<int:id_esp>")
@login_required
def nueva_version(id_esp):
    esp = storage.obtener(id_esp)
    if not esp:
        abort(404)
    tipo = esp["tipo"]
    if tipo not in TIPOS:
        abort(404)

    datos = json.loads(esp["datos_json"])

    # Campos que NO deben volver al form
    excluir = {"logo_base64", "tipo_nombre", "fecha_generacion",
               "usuario", "revision_str", "codigo_completo"}
    datos_limpios = {k: v for k, v in datos.items() if k not in excluir}

    prefill = {
        **datos_limpios,
        "codigo_base": esp["codigo_base"],
        "variante":    esp["variante"],
        "revision":    storage.siguiente_revision(esp["codigo_base"], esp["variante"]),
        "revision_str": f"{storage.siguiente_revision(esp['codigo_base'], esp['variante']):02d}",
    }
    original = {
        **datos_limpios,
        "codigo_base": esp["codigo_base"],
        "variante":    esp["variante"],
        "revision":    esp["revision"],
        "revision_str": f"{esp['revision']:02d}",
    }

    return render_template(
        _template_formulario(tipo),
        tipo=tipo, tipo_info=TIPOS[tipo],
        prefill=prefill,
        original=original,
        origen_id=id_esp,
        **_contexto_base(),
    )


# ─────────────────────────────────────────────
# Generar + guardar
# ─────────────────────────────────────────────
@pdf_bp.route("/especificaciones-pdf/tipo/<tipo>/pdf", methods=["POST"])
@login_required
def generar(tipo):
    if tipo not in TIPOS:
        abort(404)

    datos = request.form.to_dict()
    origen_id = datos.get("origen_id", "").strip()

    codigo_base = datos.get("codigo_base", "").strip().upper()
    variante    = datos.get("variante", "").strip().upper()

    if not codigo_base:
        flash("El código base es obligatorio", "danger")
        return redirect(url_for("pdf_generator.formulario", tipo=tipo))

    try:
        revision = int(datos.get("revision_str", "0"))
    except ValueError:
        revision = 0

    # ─── Prevenir duplicados lógicos ───
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("""
        SELECT id FROM especificaciones_generadas
        WHERE codigo_base = ? AND variante = ? AND revision = ? AND tipo = ?
    """, (codigo_base, variante, revision, tipo))
    existente = cur.fetchone()
    conn.close()

    if existente:
        flash(
            f"Ya existe {codigo_base}{variante} rev {revision:02d} para {tipo}. "
            f"Cambiá la variante o la revisión para guardarlo como nueva versión.",
            "danger"
        )
        return redirect(url_for("pdf_generator.formulario", tipo=tipo))

    # ─── Validación de versión si viene de una base ───
    if origen_id:
        try:
            origen_id_int = int(origen_id)
        except ValueError:
            origen_id_int = None

        if origen_id_int:
            orig = storage.obtener(origen_id_int)
            if orig:
                orig_datos = json.loads(orig["datos_json"])

                campos_excluidos = {
                    "codigo_base", "variante", "revision", "revision_str",
                    "codigo_completo", "usuario", "fecha_generacion",
                    "tipo_nombre", "logo_base64", "pagina_actual",
                    "incluir_anexo", "es_preliminar", "origen_id",
                    "imagen_planteo_base64", "versiones_anteriores",
                }

                contenido_cambio = False
                for k, v in datos.items():
                    if k in campos_excluidos:
                        continue
                    orig_val = str(orig_datos.get(k, "") or "").strip()
                    if str(v or "").strip() != orig_val:
                        contenido_cambio = True
                        break

                misma_variante = (variante == orig["variante"])
                misma_revision = (revision == orig["revision"])
                mismo_codigo   = (codigo_base == orig["codigo_base"])

                if contenido_cambio and mismo_codigo and misma_variante and misma_revision:
                    flash(
                        "Modificaste el contenido: cambiá la variante o la revisión "
                        "para guardarlo como nueva versión.",
                        "danger"
                    )
                    return redirect(url_for("pdf_generator.nueva_version",
                                            id_esp=origen_id_int))

    # ─── Completar datos auto-generados ───
    datos.update({
        "codigo_base":       codigo_base,
        "variante":          variante,
        "revision_str":      f"{revision:02d}",
        "codigo_completo":   storage.codigo_completo(codigo_base, variante),
        "usuario":           session.get("username", ""),
        "fecha_generacion":  datetime.now().strftime("%d/%m/%Y %H:%M"),
        "tipo_nombre":       TIPOS[tipo]["nombre"],
        "es_preliminar":     "1" if datos.get("es_preliminar") == "1" else "",
    })

    # ─── Armar listas para tablas dinámicas ───
    TABLAS_DINAMICAS = {
        'p1':      ['param', 'valor', 'metodo'],
        'barrera': ['param', 'valor', 'metodo'],
        'ps':      ['param', 'valor'],
        'quim':    ['param', 'valor', 'metodo'],
        'fis':     ['param', 'valor'],
    }
    for prefijo, columnas in TABLAS_DINAMICAS.items():
        filas = []
        i = 1
        while True:
            fila = {}
            hay_alguno = False
            for col in columnas:
                k = f'{prefijo}_fila{i}_{col}'
                v = datos.get(k, '')
                if v:
                    hay_alguno = True
                fila[col] = v
            if not hay_alguno:
                break
            filas.append(fila)
            i += 1
            if i > 30:
                break
        datos[f'{prefijo}_filas'] = filas

    # ─── Anexo: versiones anteriores + versión actual ───
    if datos.get("incluir_anexo"):
        anteriores = storage.versiones_con_anexo(codigo_base) if codigo_base else []
        actual = {
            'fecha_revision': datos.get("fecha_revision", "") or "—",
            'revision':       f"{revision:02d}",
            'anexo':          datos.get("anexo_detalle_cambios", "") or "—",
        }
        datos["versiones_anteriores"] = anteriores + [actual]
    else:
        datos["versiones_anteriores"] = []

    # ─── Generar PDF ───
    pdf_bytes = generar_pdf(tipo, datos)

    # ─── Guardar ───
    id_esp = storage.guardar_especificacion(
        id_usuario=session.get("user_id"),
        usuario_nombre=session.get("username", ""),
        tipo=tipo,
        codigo_base=codigo_base,
        variante=variante,
        revision=revision,
        titulo=datos.get("titulo", ""),
        cliente=datos.get("cliente", ""),
        producto=datos.get("producto", ""),
        datos=datos,
        pdf_bytes=pdf_bytes,
    )

    flash(f"Especificación {datos['codigo_completo']} rev {revision:02d} generada", "success")
    return redirect(url_for("pdf_generator.ver", id_esp=id_esp))

# ─────────────────────────────────────────────
# Visor / descarga / raw
# ─────────────────────────────────────────────
@pdf_bp.route("/especificaciones-pdf/ver/<int:id_esp>")
@login_required
def ver(id_esp):
    esp = storage.obtener(id_esp)
    if not esp:
        abort(404)
    familia = storage.versiones_de_familia(esp["codigo_base"])
    return render_template("visor.html", esp=esp, familia=familia, **_contexto_base())


@pdf_bp.route("/especificaciones-pdf/descargar/<int:id_esp>")
@login_required
def descargar(id_esp):
    esp = storage.obtener(id_esp)
    if not esp:
        abort(404)
    ruta = storage.ruta_absoluta(esp)
    if not ruta.exists():
        abort(404)
    nombre = f"{esp['codigo_completo']}_rev{esp['revision']:02d}.pdf"
    response = send_file(ruta, mimetype="application/pdf",
                         as_attachment=True, download_name=nombre)
    response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
    response.headers['Pragma'] = 'no-cache'
    response.headers['Expires'] = '0'
    return response


@pdf_bp.route("/especificaciones-pdf/raw/<int:id_esp>")
@login_required
def raw(id_esp):
    esp = storage.obtener(id_esp)
    if not esp:
        abort(404)
    ruta = storage.ruta_absoluta(esp)
    if not ruta.exists():
        abort(404)
    response = send_file(ruta, mimetype="application/pdf", as_attachment=False)
    response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
    response.headers['Pragma'] = 'no-cache'
    response.headers['Expires'] = '0'
    return response


# ─────────────────────────────────────────────
# Eliminar
# ─────────────────────────────────────────────
@pdf_bp.route("/especificaciones-pdf/eliminar/<int:id_esp>", methods=["POST"])
@login_required
def eliminar(id_esp):
    esp = storage.obtener(id_esp)
    if not esp:
        flash("Especificación no encontrada", "danger")
        return redirect(url_for("pdf_generator.panel"))

    ruta = storage.ruta_absoluta(esp)
    if ruta.exists():
        try:
            ruta.unlink()
        except Exception as e:
            print(f"⚠️  No se pudo borrar el archivo {ruta}: {e}")

    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("DELETE FROM especificaciones_generadas WHERE id = ?", (id_esp,))
    conn.commit()
    conn.close()

    flash(
        f"Especificación {esp['codigo_completo']} rev {esp['revision']:02d} eliminada",
        "success"
    )

    familia = storage.versiones_de_familia(esp["codigo_base"])
    if familia:
        return redirect(url_for("pdf_generator.ver", id_esp=familia[0]["id"]))
    return redirect(url_for("pdf_generator.panel"))


# ─────────────────────────────────────────────
# Buscador por tipo
# ─────────────────────────────────────────────
@pdf_bp.route("/especificaciones-pdf/tipo/<tipo>/buscar")
@login_required
def buscar_tipo(tipo):
    if tipo not in TIPOS:
        abort(404)
    return render_template(
        "buscar.html",
        tipo=tipo, tipo_info=TIPOS[tipo],
        **_contexto_base(),
    )


@pdf_bp.route("/especificaciones-pdf/buscar")
@login_required
def api_buscar():
    """API JSON para búsqueda por AJAX."""
    tipo = request.args.get("tipo", "").strip() or None
    q    = request.args.get("q", "").strip()
    if tipo and tipo not in TIPOS:
        tipo = None
    resultados = storage.buscar_especificaciones(tipo=tipo, q=q)
    return {"success": True, "resultados": resultados}


# ─────────────────────────────────────────────
# API versiones (para anexo automático)
# ─────────────────────────────────────────────
@pdf_bp.route("/especificaciones-pdf/api/versiones/<codigo_base>")
@login_required
def api_versiones(codigo_base):
    codigo_base = codigo_base.strip().upper()
    if not codigo_base:
        return {"existe": False, "total": 0, "versiones": []}

    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("""
        SELECT id, codigo_completo, variante, revision, tipo,
               fecha_generacion, usuario_nombre
        FROM especificaciones_generadas
        WHERE codigo_base = ?
        ORDER BY variante, revision
    """, (codigo_base,))
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()

    return {
        "existe": len(rows) > 0,
        "total":  len(rows),
        "versiones": rows,
    }


# ─────────────────────────────────────────────
# Verificación de imagen en tiempo real
# ─────────────────────────────────────────────
@pdf_bp.route("/especificaciones-pdf/verificar-imagen")
@login_required
def verificar_imagen_route():
    from pdf_utils import verificar_imagen
    url = request.args.get("url", "").strip()
    valida, mensaje = verificar_imagen(url)
    return {"valida": valida, "mensaje": mensaje}


# ─────────────────────────────────────────────
# Subida de archivos (imágenes locales)
# ─────────────────────────────────────────────
@pdf_bp.route("/especificaciones-pdf/subir-imagen", methods=["POST"])
@login_required
def subir_imagen():
    if 'archivo' not in request.files:
        return {"ok": False, "error": "No se envió archivo"}, 400

    archivo = request.files['archivo']
    if not archivo.filename:
        return {"ok": False, "error": "Nombre vacío"}, 400

    ext = Path(archivo.filename).suffix.lower()
    if ext not in EXTENSIONES_PERMITIDAS:
        return {"ok": False, "error": f"Extensión no permitida: {ext}"}, 400

    nombre_seguro = secure_filename(archivo.filename)
    nombre_final  = f"{uuid_lib.uuid4().hex}_{nombre_seguro}"
    ruta          = UPLOADS_DIR / nombre_final

    archivo.save(ruta)

    return {
        "ok": True,
        "ruta": nombre_final,
        "url_preview": url_for("pdf_generator.servir_upload", nombre=nombre_final),
    }


@pdf_bp.route("/especificaciones-pdf/uploads/<path:nombre>")
@login_required
def servir_upload(nombre):
    return send_from_directory(UPLOADS_DIR, nombre)