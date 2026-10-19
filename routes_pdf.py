# routes_pdf.py
from flask import (
    Blueprint, render_template, request, session,
    abort, send_file, redirect, url_for, flash,
    send_from_directory,
)
from datetime import datetime
from pathlib import Path
import hashlib
import io
import json
import uuid as uuid_lib

from werkzeug.utils import secure_filename

from db import get_db_connection
from permisos import login_required
from pdf_utils import generar_pdf
import storage


UPLOADS_DIR = Path(__file__).parent / "uploads"
UPLOADS_DIR.mkdir(exist_ok=True)

EXTENSIONES_PERMITIDAS = {'.png', '.jpg', '.jpeg', '.gif', '.webp', '.bmp'}
HASHES_FILE = UPLOADS_DIR / "_hashes.json"

MAX_BORRADORES_POR_USUARIO = 10

pdf_bp = Blueprint("pdf_generator", __name__, template_folder="templates")


TIPOS = {
    "diseno_grafico":   {"nombre": "Diseño Gráfico",      "icono": "fas fa-drafting-compass", "color": "primary"},
    "material_empaque": {"nombre": "Material de Empaque", "icono": "fas fa-box",              "color": "success"},
    "etiqueta":         {"nombre": "Etiqueta",            "icono": "fas fa-tag",              "color": "warning"},
    "etiqueta_zebra":   {"nombre": "Etiqueta Zebra",      "icono": "fas fa-barcode",          "color": "danger"},
}


def _template_formulario(tipo: str) -> str:
    templates = {
        'material_empaque': 'formulario_material_empaque.html',
        'etiqueta':         'formulario_etiqueta.html',
    }
    return templates.get(tipo, 'formulario.html')


def _contexto_base():
    return {
        "tipos":     TIPOS,
        "usuario":   session.get("username", ""),
        "es_admin":  session.get("es_admin", False),
        "user_id":   session.get("user_id"),
    }


def _cargar_hashes() -> dict:
    if HASHES_FILE.exists():
        try:
            return json.loads(HASHES_FILE.read_text(encoding='utf-8'))
        except Exception:
            return {}
    return {}


def _guardar_hashes(d: dict) -> None:
    try:
        HASHES_FILE.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding='utf-8')
    except Exception as e:
        print(f"⚠️  No se pudo guardar {HASHES_FILE}: {e}")


# ─────────────────────────────────────────────
# Utilidades
# ─────────────────────────────────────────────
def _armar_filas_dinamicas(datos: dict) -> dict:
    TABLAS = {
        'p1':       ['param', 'valor', 'metodo'],
        'barrera':  ['param', 'valor', 'metodo'],
        'ps':       ['param', 'valor'],
        'quim':     ['param', 'valor', 'metodo'],
        'fis':      ['param', 'valor'],
        'elemento': ['num', 'nombre', 'items', 'criterios'],
        'dim':      ['param', 'medida', 'metodo'],
        'embalaje': ['titulo', 'texto'],
    }
    for prefijo, columnas in TABLAS.items():
        filas = []
        i = 1
        while True:
            fila = {}
            hay = False
            for col in columnas:
                k = f'{prefijo}_fila{i}_{col}'
                v = datos.get(k, '')
                if v:
                    hay = True
                fila[col] = v
            if not hay:
                break
            if not fila.get('num'):
                fila['num'] = str(i - 1)
            filas.append(fila)
            i += 1
            if i > 30:
                break
        datos[f'{prefijo}_filas'] = filas
    return datos


def _completar_datos_autogenerados(datos: dict, tipo: str, codigo_base: str,
                                  variante: str, revision: int) -> dict:
    datos.update({
        "codigo_base":      codigo_base,
        "variante":         variante,
        "revision_str":     f"{revision:02d}",
        "codigo_completo":  storage.codigo_completo(codigo_base, variante),
        "usuario":          session.get("username", ""),
        "fecha_generacion": datetime.now().strftime("%d/%m/%Y %H:%M"),
        "tipo_nombre":      TIPOS[tipo]["nombre"],
        "es_preliminar":    "1" if datos.get("es_preliminar") == "1" else "",
    })
    return datos


def _armar_anexo(datos: dict, codigo_base: str, tipo: str, revision: int) -> dict:
    if datos.get("incluir_anexo"):
        anteriores = storage.versiones_con_anexo(codigo_base, tipo)
        actual = {
            'fecha_revision': datos.get("fecha_revision", "") or "—",
            'revision':       f"{revision:02d}",
            'anexo':          datos.get("anexo_detalle_cambios", "") or "—",
        }
        datos["versiones_anteriores"] = anteriores + [actual]
    else:
        datos["versiones_anteriores"] = []
    return datos


def _validar_y_completar_datos(tipo: str):
    """Devuelve (datos, error_dict)."""
    if tipo not in TIPOS:
        return None, {"error": "tipo_invalido", "msg": f"Tipo inválido: {tipo}"}

    datos = request.form.to_dict()
    codigo_base = datos.get("codigo_base", "").strip().upper()
    variante    = datos.get("variante", "").strip().upper()

    if not codigo_base:
        return None, {"error": "sin_codigo", "msg": "El código base es obligatorio"}

    try:
        revision = int(datos.get("revision_str", "0"))
    except ValueError:
        revision = 0

    datos = _completar_datos_autogenerados(datos, tipo, codigo_base, variante, revision)
    datos = _armar_filas_dinamicas(datos)
    datos = _armar_anexo(datos, codigo_base, tipo, revision)
    return datos, None


def _generar_pdf_bytes(tipo: str, datos: dict):
    try:
        return generar_pdf(tipo, datos)
    except Exception as e:
        print(f"⚠️  Error generando PDF: {e}")
        return None


# ─────────────────────────────────────────────
# Usuarios
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

    cur.execute("""INSERT INTO usuarios (nombre, password_hash, activo, es_admin)
                   VALUES (?, ?, 1, ?)""",
                (nombre, generate_password_hash(password), 1 if es_admin else 0))
    nuevo_id = cur.lastrowid
    # Dar acceso a la sección de especificaciones
    cur.execute("""INSERT OR IGNORE INTO permisos_usuario_seccion (id_usuario, seccion)
                   VALUES (?, 'especificaciones')""", (nuevo_id,))
    conn.commit()
    conn.close()
    return {"success": True, "mensaje": f"Usuario {nombre} creado"}


# ─────────────────────────────────────────────
# Panel principal (3 columnas)
# ─────────────────────────────────────────────
@pdf_bp.route("/especificaciones-pdf")
@pdf_bp.route("/especificaciones-pdf/")
@login_required
def panel():
    user_id  = session.get("user_id")
    es_admin = session.get("es_admin", False)

    publicadas  = storage.ultimas_publicadas(limite=20)
    mis_borr    = storage.listar_borradores_usuario(user_id)
    compartidos = storage.borradores_compartidos_conmigo(user_id, es_admin=es_admin)

    return render_template("panel.html",
                           ultimas=publicadas,
                           borradores=mis_borr,
                           compartidos=compartidos,
                           max_borradores=MAX_BORRADORES_POR_USUARIO,
                           **_contexto_base())


# ─────────────────────────────────────────────
# Formularios
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
        borrador_id=None,
        borrador=None,
        permisos=None,
        otro_editando=None,
        **_contexto_base(),
    )


@pdf_bp.route("/especificaciones-pdf/borrador/<int:id_b>")
@login_required
def formulario_borrador(id_b):
    b = storage.obtener_borrador(id_b)
    if not b:
        abort(404)

    user_id  = session.get("user_id")
    es_admin = session.get("es_admin", False)

    permisos = storage.calcular_permisos_borrador(id_b, user_id, es_admin)
    if not permisos or not permisos["puede_ver"]:
        abort(403)

    tipo = b["tipo"]
    if tipo not in TIPOS:
        abort(404)

    try:
        datos = json.loads(b["datos_json"] or "{}")
    except Exception:
        datos = {}

    # Marcar edición activa y consultar si hay otro
    storage.marcar_edicion_activa(id_b, user_id)
    otro_editando = storage.quien_esta_editando(id_b, id_usuario_actual=user_id)

    return render_template(
        _template_formulario(tipo),
        tipo=tipo, tipo_info=TIPOS[tipo],
        prefill=datos,
        original=None,
        origen_id=None,
        borrador_id=id_b,
        borrador=b,
        permisos=permisos,
        otro_editando=otro_editando,
        **_contexto_base(),
    )


@pdf_bp.route("/especificaciones-pdf/nueva-version/<int:id_esp>")
@login_required
def nueva_version(id_esp):
    esp = storage.obtener(id_esp)
    if not esp:
        abort(404)

    tipo = esp["tipo"]
    if tipo not in TIPOS:
        abort(404)

    # Si ya hay un borrador de la familia, redirigimos a editarlo.
    b_existente = storage.obtener_borrador_de_familia(
        esp["codigo_base"], esp["variante"], tipo
    )
    if b_existente:
        flash(
            f"Ya tenés un borrador activo para {esp['codigo_base']}{esp['variante']} "
            f"(rev {b_existente['revision']:02d}). Te llevamos ahí.",
            "warning"
        )
        return redirect(url_for("pdf_generator.formulario_borrador", id_b=b_existente["id"]))

    try:
        datos = json.loads(esp["datos_json"] or "{}")
    except Exception:
        datos = {}

    excluir = {"logo_base64", "tipo_nombre", "fecha_generacion",
               "usuario", "revision_str", "codigo_completo"}
    datos_limpios = {k: v for k, v in datos.items() if k not in excluir}

    siguiente = storage.siguiente_revision(esp["codigo_base"], esp["variante"], tipo)
    prefill = {
        **datos_limpios,
        "codigo_base":  esp["codigo_base"],
        "variante":     esp["variante"],
        "revision_str": f"{siguiente:02d}",
    }
    original = {
        **datos_limpios,
        "codigo_base":  esp["codigo_base"],
        "variante":     esp["variante"],
        "revision":     esp["revision"],
        "revision_str": f"{esp['revision']:02d}",
        "es_para_crear_a_partir_de": False,
    }

    return render_template(
        _template_formulario(tipo),
        tipo=tipo, tipo_info=TIPOS[tipo],
        prefill=prefill,
        original=original,
        origen_id=id_esp,
        borrador_id=None,
        borrador=None,
        permisos=None,
        otro_editando=None,
        **_contexto_base(),
    )

@pdf_bp.route("/especificaciones-pdf/crear-a-partir-de/<int:id_esp>")
@login_required
def crear_a_partir_de(id_esp):
    """
    Precarga TODOS los datos del documento origen.
    - Si el usuario deja código + variante iguales → la revisión sigue la
      numeración (última + 1).
    - Si cambia código o variante → la revisión vuelve a 00.
    """
    esp = storage.obtener(id_esp)
    if not esp:
        abort(404)

    tipo = esp["tipo"]
    if tipo not in TIPOS:
        abort(404)

    try:
        datos = json.loads(esp["datos_json"] or "{}")
    except Exception:
        datos = {}

    excluir = {"logo_base64", "tipo_nombre", "fecha_generacion",
               "usuario", "revision_str", "codigo_completo",
               "nombre_descarga", "versiones_anteriores"}
    datos_limpios = {k: v for k, v in datos.items() if k not in excluir}

    siguiente = storage.siguiente_revision(esp["codigo_base"], esp["variante"], tipo)

    prefill = {
        **datos_limpios,
        "codigo_base":  esp["codigo_base"],
        "variante":     esp["variante"],
        "revision_str": f"{siguiente:02d}",
    }
    # "original" en este modo representa el documento de referencia,
    # para que el JS sepa cuándo recalcular la revisión.
    original = {
        "codigo_base":  esp["codigo_base"],
        "variante":     esp["variante"],
        "revision_str": f"{siguiente:02d}",
        "es_para_crear_a_partir_de": True,
    }

    return render_template(
        _template_formulario(tipo),
        tipo=tipo, tipo_info=TIPOS[tipo],
        prefill=prefill,
        original=original,
        origen_id=None,
        crear_a_partir_de_id=id_esp,
        borrador_id=None,
        borrador=None,
        permisos=None,
        otro_editando=None,
        **_contexto_base(),
    )

# ─────────────────────────────────────────────
# GUARDAR BORRADOR (con chequeo de permisos)
# ─────────────────────────────────────────────
@pdf_bp.route("/especificaciones-pdf/tipo/<tipo>/borrador", methods=["POST"])
@login_required
def guardar_borrador(tipo):
    if tipo not in TIPOS:
        abort(404)

    datos, err = _validar_y_completar_datos(tipo)
    if err:
        flash(err["msg"], "danger")
        return redirect(url_for("pdf_generator.formulario", tipo=tipo))

    id_b_str = datos.pop("borrador_id", "").strip()
    user_id  = session.get("user_id")
    es_admin = session.get("es_admin", False)

    codigo_base = datos["codigo_base"]
    variante    = datos["variante"]
    revision    = int(datos["revision_str"])

    if id_b_str:
        try:
            id_b = int(id_b_str)
        except ValueError:
            id_b = None

        b = storage.obtener_borrador(id_b) if id_b else None
        if not b:
            flash("Borrador no encontrado", "danger")
            return redirect(url_for("pdf_generator.panel"))

        permisos = storage.calcular_permisos_borrador(id_b, user_id, es_admin)
        if not permisos or not permisos["puede_editar"]:
            flash("No tenés permiso para editar este borrador.", "danger")
            return redirect(url_for("pdf_generator.panel"))

        # ─── Bloqueo optimista ───
        fecha_orig = datos.pop("fecha_actualizacion_original", "").strip()
        if storage.borrador_cambio_desde(id_b, fecha_orig):
            flash(
                "Este borrador fue modificado por otro usuario mientras lo editabas. "
                "Tus cambios NO se guardaron. Cargando la última versión.",
                "warning"
            )
            return redirect(url_for("pdf_generator.formulario_borrador", id_b=id_b))

        storage.actualizar_borrador(
            id_b,
            titulo   = datos.get("titulo", ""),
            cliente  = datos.get("cliente", ""),
            producto = datos.get("producto", ""),
            datos    = datos,
        )
        # Refrescar marca de edición activa
        storage.marcar_edicion_activa(id_b, user_id)
        flash("Borrador actualizado", "success")
        return redirect(url_for("pdf_generator.formulario_borrador", id_b=id_b))

    # Crear borrador nuevo
    if storage.contar_borradores(user_id) >= MAX_BORRADORES_POR_USUARIO:
        flash(f"Llegaste al máximo de {MAX_BORRADORES_POR_USUARIO} borradores. "
              f"Publicá o eliminá alguno para continuar.", "danger")
        return redirect(url_for("pdf_generator.formulario", tipo=tipo))

    existente = storage.obtener_borrador_de_familia(codigo_base, variante, tipo)
    if existente:
        flash(f"Ya existe un borrador para {codigo_base}{variante} "
              f"(rev {existente['revision']:02d}).", "warning")
        return redirect(url_for("pdf_generator.formulario_borrador", id_b=existente["id"]))

    if storage.existe_publicado(codigo_base, variante, revision, tipo):
        flash(f"La revisión {revision:02d} ya fue publicada. "
              f"Usá una revisión mayor.", "danger")
        return redirect(url_for("pdf_generator.formulario", tipo=tipo))

    id_b = storage.crear_borrador(
        id_usuario      = user_id,
        usuario_nombre  = session.get("username", ""),
        tipo            = tipo,
        codigo_base     = codigo_base,
        variante        = variante,
        revision        = revision,
        titulo          = datos.get("titulo", ""),
        cliente         = datos.get("cliente", ""),
        producto        = datos.get("producto", ""),
        datos           = datos,
    )
    flash(f"Borrador guardado: {codigo_base}{variante} rev {revision:02d}", "success")
    return redirect(url_for("pdf_generator.formulario_borrador", id_b=id_b))


# ─────────────────────────────────────────────
# ELIMINAR BORRADOR
# ─────────────────────────────────────────────
@pdf_bp.route("/especificaciones-pdf/borrador/<int:id_b>/eliminar", methods=["POST"])
@login_required
def eliminar_borrador(id_b):
    b = storage.obtener_borrador(id_b)
    if not b:
        flash("Borrador no encontrado", "danger")
        return redirect(url_for("pdf_generator.panel"))

    user_id  = session.get("user_id")
    es_admin = session.get("es_admin", False)

    permisos = storage.calcular_permisos_borrador(id_b, user_id, es_admin)
    if not permisos or not permisos["puede_eliminar"]:
        flash("No tenés permiso para eliminar este borrador.", "danger")
        return redirect(url_for("pdf_generator.panel"))

    storage.eliminar_borrador(id_b)
    flash(f"Borrador {b['codigo_completo']} rev {b['revision']:02d} eliminado", "success")
    return redirect(url_for("pdf_generator.panel"))


# ─────────────────────────────────────────────
# PUBLICAR
# ─────────────────────────────────────────────
@pdf_bp.route("/especificaciones-pdf/tipo/<tipo>/publicar", methods=["POST"])
@login_required
def publicar(tipo):
    if tipo not in TIPOS:
        abort(404)

    datos, err = _validar_y_completar_datos(tipo)
    if err:
        flash(err["msg"], "danger")
        return redirect(url_for("pdf_generator.formulario", tipo=tipo))

    id_b_str = datos.pop("borrador_id", "").strip()
    user_id  = session.get("user_id")
    es_admin = session.get("es_admin", False)

    codigo_base = datos["codigo_base"]
    variante    = datos["variante"]
    revision    = int(datos["revision_str"])

    if storage.existe_publicado(codigo_base, variante, revision, tipo):
        flash(f"Ya existe {codigo_base}{variante} rev {revision:02d}.", "danger")
        return redirect(url_for("pdf_generator.formulario", tipo=tipo))

    # Validar plantilla
    pdf_bytes = _generar_pdf_bytes(tipo, datos)
    if pdf_bytes is None:
        flash("Error generando el PDF. Revisá la plantilla o los datos.", "danger")
        return redirect(url_for("pdf_generator.formulario", tipo=tipo))

    fecha_rev = (datos.get("fecha_revision") or "").strip()
    nombre_descarga = storage.nombre_pdf_visible(tipo, codigo_base, variante, fecha_rev)

    id_publicado = None
    if id_b_str:
        try:
            id_b = int(id_b_str)
        except ValueError:
            id_b = None
        if id_b:
            b = storage.obtener_borrador(id_b)
            if not b:
                flash("Borrador no encontrado.", "danger")
                return redirect(url_for("pdf_generator.panel"))

            permisos = storage.calcular_permisos_borrador(id_b, user_id, es_admin)
            if not permisos or not permisos["puede_publicar"]:
                flash("No tenés permiso para publicar este borrador.", "danger")
                return redirect(url_for("pdf_generator.panel"))

            # ─── Bloqueo optimista ───
            fecha_orig = datos.pop("fecha_actualizacion_original", "").strip()
            if storage.borrador_cambio_desde(id_b, fecha_orig):
                flash(
                    "Este borrador fue modificado por otro usuario mientras lo editabas. "
                    "Revisá la última versión antes de publicar.",
                    "warning"
                )
                return redirect(url_for("pdf_generator.formulario_borrador", id_b=id_b))

            storage.actualizar_borrador(
                id_b,
                titulo=datos.get("titulo", ""),
                cliente=datos.get("cliente", ""),
                producto=datos.get("producto", ""),
                datos=datos,
            )
            id_publicado = storage.publicar_borrador(id_b, nombre_descarga=nombre_descarga)
            storage.limpiar_edicion_activa(id_b, user_id)

            # Notificar al dueño si publicó otro usuario
            if b["id_usuario"] != user_id:
                storage.crear_notificacion(
                    b["id_usuario"],
                    f"{b['codigo_completo']} fue publicado por {session.get('username')}",
                    url=url_for("pdf_generator.ver", id_esp=id_publicado)
                )

    if id_publicado is None:
        id_publicado = storage.guardar_publicado(
            id_usuario      = user_id,
            usuario_nombre  = session.get("username", ""),
            tipo            = tipo,
            codigo_base     = codigo_base,
            variante        = variante,
            revision        = revision,
            titulo          = datos.get("titulo", ""),
            cliente         = datos.get("cliente", ""),
            producto        = datos.get("producto", ""),
            nombre_descarga = nombre_descarga,
            datos           = datos,
        )

    storage.bump_drafts_after_publish(codigo_base, variante, tipo, revision)

    flash(f"Publicado: {codigo_base}{variante} rev {revision:02d}", "success")
    return redirect(url_for("pdf_generator.ver", id_esp=id_publicado))


# ─────────────────────────────────────────────
# GENERAR TEMPORAL (sin guardar)
# ─────────────────────────────────────────────
@pdf_bp.route("/especificaciones-pdf/tipo/<tipo>/temporal", methods=["POST"])
@login_required
def generar_temporal(tipo):
    if tipo not in TIPOS:
        abort(404)

    datos, err = _validar_y_completar_datos(tipo)
    if err:
        flash(err["msg"], "danger")
        return redirect(url_for("pdf_generator.formulario", tipo=tipo))

    datos.pop("borrador_id", None)
    datos.pop("fecha_actualizacion_original", None)

    pdf_bytes = _generar_pdf_bytes(tipo, datos)
    if pdf_bytes is None:
        flash("Error generando el PDF.", "danger")
        return redirect(url_for("pdf_generator.formulario", tipo=tipo))

    codigo_base = datos["codigo_base"]
    variante    = datos["variante"]
    fecha_rev   = (datos.get("fecha_revision") or "").strip()
    nombre = storage.nombre_pdf_visible(tipo, codigo_base, variante, fecha_rev)

    response = send_file(
        io.BytesIO(pdf_bytes),
        mimetype="application/pdf",
        as_attachment=True,
        download_name=nombre,
    )
    response.headers['Cache-Control'] = 'no-store'
    return response


# ─────────────────────────────────────────────
# Visor / descarga / raw
# ─────────────────────────────────────────────
@pdf_bp.route("/especificaciones-pdf/ver/<int:id_esp>")
@login_required
def ver(id_esp):
    esp = storage.obtener(id_esp)
    if not esp:
        abort(404)
    familia = storage.versiones_de_familia(esp["codigo_base"], tipo=esp["tipo"])
    return render_template("visor.html", esp=esp, familia=familia, **_contexto_base())


def _pdf_de_publicado(id_esp: int):
    esp = storage.obtener(id_esp)
    if not esp:
        return None, None
    datos = storage.obtener_datos(id_esp)
    if not datos:
        return None, esp
    pdf_bytes = _generar_pdf_bytes(esp["tipo"], datos)
    return pdf_bytes, esp


def _nombre_descarga_de(esp: dict) -> str:
    """Devuelve el nombre 'lindo' para descargar/visor, con fallback."""
    nombre = esp.get("nombre_descarga")
    if nombre:
        return nombre
    try:
        datos = json.loads(esp["datos_json"] or "{}")
    except Exception:
        datos = {}
    return storage.nombre_pdf_visible(
        esp["tipo"], esp["codigo_base"], esp["variante"],
        datos.get("fecha_revision", "")
    )


@pdf_bp.route("/especificaciones-pdf/descargar/<int:id_esp>")
@login_required
def descargar(id_esp):
    pdf_bytes, esp = _pdf_de_publicado(id_esp)
    if not esp:
        abort(404)
    if pdf_bytes is None:
        abort(500, "Error generando PDF")

    nombre = _nombre_descarga_de(esp)

    response = send_file(io.BytesIO(pdf_bytes),
                         mimetype="application/pdf",
                         as_attachment=True,
                         download_name=nombre)
    response.headers['Cache-Control'] = 'no-store'
    return response


@pdf_bp.route("/especificaciones-pdf/raw/<int:id_esp>")
@login_required
def raw(id_esp):
    pdf_bytes, esp = _pdf_de_publicado(id_esp)
    if not esp:
        abort(404)
    if pdf_bytes is None:
        abort(500, "Error generando PDF")

    # Usamos download_name aunque sea inline: algunos navegadores lo respetan
    # para nombrar el visor de PDF interno.
    nombre = _nombre_descarga_de(esp)

    response = send_file(io.BytesIO(pdf_bytes),
                         mimetype="application/pdf",
                         as_attachment=False,
                         download_name=nombre)
    response.headers['Cache-Control'] = 'no-store'
    return response


# ─────────────────────────────────────────────
# Eliminar publicado
# ─────────────────────────────────────────────
@pdf_bp.route("/especificaciones-pdf/eliminar/<int:id_esp>", methods=["POST"])
@login_required
def eliminar(id_esp):
    esp = storage.eliminar_publicado(id_esp)
    if not esp:
        flash("Especificación no encontrada", "danger")
        return redirect(url_for("pdf_generator.panel"))

    flash(f"Eliminado: {esp['codigo_completo']} rev {esp['revision']:02d}", "success")
    return redirect(url_for("pdf_generator.panel"))


# ─────────────────────────────────────────────
# Buscador
# ─────────────────────────────────────────────
@pdf_bp.route("/especificaciones-pdf/tipo/<tipo>/buscar")
@login_required
def buscar_tipo(tipo):
    if tipo not in TIPOS:
        abort(404)
    return render_template("buscar.html",
                           tipo=tipo, tipo_info=TIPOS[tipo],
                           **_contexto_base())


@pdf_bp.route("/especificaciones-pdf/buscar")
@login_required
def api_buscar():
    tipo = request.args.get("tipo", "").strip() or None
    q    = request.args.get("q", "").strip()
    if tipo and tipo not in TIPOS:
        tipo = None
    resultados = storage.buscar_publicadas(tipo=tipo, q=q)
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
    cur.execute("""SELECT id, codigo_completo, variante, revision, tipo,
                          fecha_generacion, usuario_nombre
                     FROM especificaciones_generadas
                    WHERE codigo_base = ?
                    ORDER BY variante, revision""", (codigo_base,))
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    return {"existe": len(rows) > 0, "total": len(rows), "versiones": rows}


@pdf_bp.route("/especificaciones-pdf/api/borrador-familia/<codigo_base>/<tipo>")
@login_required
def api_borrador_familia(codigo_base, tipo):
    codigo_base = codigo_base.strip().upper()
    variante = request.args.get("variante", "").strip().upper()
    b = storage.obtener_borrador_de_familia(codigo_base, variante, tipo)
    if not b:
        return {"existe": False}
    return {"existe": True, "id": b["id"], "revision": b["revision"]}


# ═══════════════════════════════════════════════
# COMPARTIR
# ═══════════════════════════════════════════════
@pdf_bp.route("/especificaciones-pdf/api/usuarios-compartir")
@login_required
def api_usuarios_compartir():
    """Lista de usuarios con acceso a la sección, sin el usuario actual."""
    user_id = session.get("user_id")
    usuarios = storage.usuarios_con_acceso_seccion("especificaciones")
    usuarios = [u for u in usuarios if u["id"] != user_id]
    return {"success": True, "usuarios": usuarios}


@pdf_bp.route("/especificaciones-pdf/api/permisos-globales")
@login_required
def api_permisos_globales():
    id_dueno = request.args.get("id_dueno", type=int) or session.get("user_id")
    if id_dueno != session.get("user_id") and not session.get("es_admin"):
        abort(403)
    return {"success": True, "permisos": storage.obtener_permisos_globales(id_dueno)}


@pdf_bp.route("/especificaciones-pdf/api/permisos-globales", methods=["POST"])
@login_required
def api_set_permisos_globales():
    data = request.get_json() or {}
    id_dueno = data.get("id_dueno") or session.get("user_id")

    if id_dueno != session.get("user_id") and not session.get("es_admin"):
        abort(403)

    # Set anterior de usuarios con permiso
    anteriores = storage.obtener_permisos_globales(id_dueno)
    ids_antes = {p["id_usuario"] for p in anteriores}

    permisos = data.get("permisos", [])
    storage.set_permisos_globales(id_dueno, permisos)

    # Detectar removidos → notificar
    ids_ahora = {int(p["id_usuario"]) for p in permisos}
    removidos = ids_antes - ids_ahora
    if removidos:
        nombre_dueno = session.get("username", "")
        for uid in removidos:
            storage.crear_notificacion(
                uid,
                f"{nombre_dueno} te revocó el acceso a su banco de borradores.",
                url=url_for("pdf_generator.panel")
            )

    return {"success": True}


@pdf_bp.route("/especificaciones-pdf/api/permisos-borrador/<int:id_b>")
@login_required
def api_permisos_borrador(id_b):
    b = storage.obtener_borrador(id_b)
    if not b:
        abort(404)
    if b["id_usuario"] != session.get("user_id") and not session.get("es_admin"):
        abort(403)

    especificos = storage.obtener_permisos_especificos(id_b)
    return {"success": True, "permisos": especificos, "id_dueno": b["id_usuario"]}


@pdf_bp.route("/especificaciones-pdf/api/permisos-borrador/<int:id_b>", methods=["POST"])
@login_required
def api_set_permisos_borrador(id_b):
    b = storage.obtener_borrador(id_b)
    if not b:
        abort(404)
    if b["id_usuario"] != session.get("user_id") and not session.get("es_admin"):
        abort(403)

    # Set anterior de usuarios con override
    anteriores = storage.obtener_permisos_especificos(id_b)
    ids_antes = {p["id_usuario"] for p in anteriores}

    data = request.get_json() or {}
    permisos = data.get("permisos", [])
    storage.set_permisos_especificos(id_b, permisos)

    # Detectar removidos → notificar
    ids_ahora = {int(p["id_usuario"]) for p in permisos}
    removidos = ids_antes - ids_ahora
    if removidos:
        nombre_dueno = session.get("username", "")
        for uid in removidos:
            storage.crear_notificacion(
                uid,
                f"{nombre_dueno} te revocó el acceso al borrador "
                f"{b['codigo_completo']} rev {b['revision']:02d}.",
                url=url_for("pdf_generator.panel")
            )

    return {"success": True}

# ═══════════════════════════════════════════════
# NOTIFICACIONES (base para Fase 4)
# ═══════════════════════════════════════════════
@pdf_bp.route("/especificaciones-pdf/api/notificaciones")
@login_required
def api_notificaciones():
    user_id = session.get("user_id")
    no_leidas = storage.notificaciones_no_leidas(user_id)
    return {"success": True, "notificaciones": no_leidas}


@pdf_bp.route("/especificaciones-pdf/api/notificaciones/leer", methods=["POST"])
@login_required
def api_notif_marcar_leidas():
    data = request.get_json() or {}
    ids = data.get("ids")
    storage.marcar_notificaciones_leidas(session.get("user_id"), ids)
    return {"success": True}


# ─────────────────────────────────────────────
# Uploads (con dedupe)
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

    contenido = archivo.read()
    if not contenido:
        return {"ok": False, "error": "Archivo vacío"}, 400

    hash_hex = hashlib.sha256(contenido).hexdigest()
    hashes   = _cargar_hashes()

    if hash_hex in hashes:
        nombre_existente = hashes[hash_hex]
        if (UPLOADS_DIR / nombre_existente).exists():
            return {
                "ok": True, "ruta": nombre_existente, "reutilizada": True,
                "url_preview": url_for("pdf_generator.servir_upload",
                                       nombre=nombre_existente),
            }
        del hashes[hash_hex]

    nombre_seguro = secure_filename(archivo.filename)
    nombre_final  = f"{uuid_lib.uuid4().hex}_{nombre_seguro}"
    (UPLOADS_DIR / nombre_final).write_bytes(contenido)

    hashes[hash_hex] = nombre_final
    _guardar_hashes(hashes)

    return {"ok": True, "ruta": nombre_final, "reutilizada": False,
            "url_preview": url_for("pdf_generator.servir_upload", nombre=nombre_final)}


@pdf_bp.route("/especificaciones-pdf/uploads/<path:nombre>")
@login_required
def servir_upload(nombre):
    return send_from_directory(UPLOADS_DIR, nombre)


# ─────────────────────────────────────────────
# Verificación de imagen (legacy)
# ─────────────────────────────────────────────
@pdf_bp.route("/especificaciones-pdf/verificar-imagen")
@login_required
def verificar_imagen_route():
    from pdf_utils import verificar_imagen
    url = request.args.get("url", "").strip()
    valida, mensaje = verificar_imagen(url)
    return {"valida": valida, "mensaje": mensaje}

@pdf_bp.route("/especificaciones-pdf/borrador/<int:id_b>/heartbeat", methods=["POST"])
@login_required
def borrador_heartbeat(id_b):
    """Renueva la marca de 'edición activa' para este borrador."""
    b = storage.obtener_borrador(id_b)
    if not b:
        return {"success": False, "error": "no_existe"}, 404

    user_id  = session.get("user_id")
    es_admin = session.get("es_admin", False)

    permisos = storage.calcular_permisos_borrador(id_b, user_id, es_admin)
    if not permisos or not permisos["puede_ver"]:
        return {"success": False, "error": "sin_permiso"}, 403

    storage.marcar_edicion_activa(id_b, user_id)
    return {"success": True}