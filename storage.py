# storage.py
import json
import re
from datetime import datetime
from pathlib import Path

from db import get_db_connection


TIPOS_ABREV = {
    "diseno_grafico":   "DG",
    "material_empaque": "ME",
    "etiqueta":         "E",
    "etiqueta_zebra":   "ES",
}


# ─── Helpers ───
def codigo_completo(codigo_base, variante):
    return f"{(codigo_base or '').strip().upper()}{(variante or '').strip().upper()}"


def _fmt_fecha_ddmmyyyy(fecha):
    if not fecha:
        return ""
    fecha = fecha.strip()
    m = re.match(r"^(\d{4})-(\d{1,2})-(\d{1,2})$", fecha)
    if m:
        y, mo, d = m.groups()
        return f"{int(d):02d}-{int(mo):02d}-{y}"
    m = re.match(r"^(\d{1,2})[/-](\d{1,2})[/-](\d{4})$", fecha)
    if m:
        d, mo, y = m.groups()
        return f"{int(d):02d}-{int(mo):02d}-{y}"
    return fecha


def nombre_pdf_visible(tipo, codigo_base, variante, fecha_revision):
    abrev = TIPOS_ABREV.get(tipo, (tipo or "").upper()[:3])
    cod   = codigo_completo(codigo_base, variante)
    fecha = _fmt_fecha_ddmmyyyy(fecha_revision) or "SIN-FECHA"
    return f"ET-{abrev}-{cod} (Rev {fecha}).pdf"


# ─── Revisión ───
def siguiente_revision(codigo_base, variante, tipo):
    cb = codigo_base.strip().upper()
    va = (variante or "").strip().upper()
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("""
        SELECT MAX(revision) FROM (
            SELECT revision FROM especificaciones_generadas
              WHERE codigo_base = ? AND variante = ? AND tipo = ?
            UNION ALL
            SELECT revision FROM borradores
              WHERE codigo_base = ? AND variante = ? AND tipo = ?
        )
    """, (cb, va, tipo, cb, va, tipo))
    row = cur.fetchone()
    conn.close()
    max_rev = row[0] if row and row[0] is not None else -1
    return max_rev + 1


# ─── Publicados ───
def guardar_publicado(*, id_usuario, usuario_nombre, tipo, codigo_base, variante,
                     revision, titulo, cliente, producto, nombre_descarga, datos):
    cb = codigo_base.strip().upper()
    va = (variante or "").strip().upper()
    cc = codigo_completo(cb, va)

    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO especificaciones_generadas
            (id_usuario, usuario_nombre, tipo, codigo_base, variante, revision,
             codigo_completo, titulo, cliente, producto, nombre_descarga,
             datos_json, fecha_generacion)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
    """, (id_usuario, usuario_nombre, tipo, cb, va, revision, cc,
          titulo, cliente, producto, nombre_descarga,
          json.dumps(datos, ensure_ascii=False),
          datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
    new_id = cur.lastrowid
    conn.commit()
    conn.close()
    return new_id


def obtener(id_esp):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM especificaciones_generadas WHERE id = ?", (id_esp,))
    row = cur.fetchone()
    conn.close()
    return dict(row) if row else None


def obtener_datos(id_esp):
    esp = obtener(id_esp)
    if not esp:
        return {}
    try:
        return json.loads(esp.get("datos_json") or "{}")
    except Exception:
        return {}


def existe_publicado(codigo_base, variante, revision, tipo):
    cb = codigo_base.strip().upper()
    va = (variante or "").strip().upper()
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("""
        SELECT 1 FROM especificaciones_generadas
        WHERE codigo_base = ? AND variante = ? AND revision = ? AND tipo = ?
        LIMIT 1
    """, (cb, va, revision, tipo))
    row = cur.fetchone()
    conn.close()
    return row is not None


def versiones_de_familia(codigo_base, tipo=None):
    cb = codigo_base.strip().upper()
    conn = get_db_connection()
    cur = conn.cursor()
    if tipo:
        cur.execute("""
            SELECT * FROM especificaciones_generadas
            WHERE codigo_base = ? AND tipo = ?
            ORDER BY variante ASC, revision DESC
        """, (cb, tipo))
    else:
        cur.execute("""
            SELECT * FROM especificaciones_generadas
            WHERE codigo_base = ?
            ORDER BY tipo, variante ASC, revision DESC
        """, (cb,))
    rows = cur.fetchall()
    conn.close()
    return [dict(r) for r in rows]


def _marcar_ultimas(resultados: list[dict]) -> list[dict]:
    """Agrega 'es_ultima' a cada resultado: True si es la última revisión
    de su (codigo_base, variante, tipo)."""
    if not resultados:
        return resultados
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("""
        SELECT codigo_base, variante, tipo, MAX(revision) AS max_rev
          FROM especificaciones_generadas
         GROUP BY codigo_base, variante, tipo
    """)
    ultimas = {
        (r["codigo_base"], r["variante"], r["tipo"]): r["max_rev"]
        for r in cur.fetchall()
    }
    conn.close()
    for r in resultados:
        key = (r["codigo_base"], r["variante"], r["tipo"])
        r["es_ultima"] = (r["revision"] == ultimas.get(key))
    return resultados


def ultimas_publicadas(limite=20):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM especificaciones_generadas ORDER BY id DESC LIMIT ?", (limite,))
    rows = cur.fetchall()
    conn.close()
    return _marcar_ultimas([dict(r) for r in rows])


def buscar_publicadas(tipo=None, q="", limite=100):
    conn = get_db_connection()
    cur = conn.cursor()
    sql = "SELECT * FROM especificaciones_generadas WHERE 1=1"
    params = []
    if tipo:
        sql += " AND tipo = ?"
        params.append(tipo)
    if q:
        sql += """ AND (codigo_base LIKE ? OR codigo_completo LIKE ?
                       OR cliente LIKE ? OR producto LIKE ? OR titulo LIKE ?)"""
        like = f"%{q}%"
        params.extend([like] * 5)
    sql += " ORDER BY id DESC LIMIT ?"
    params.append(limite)
    cur.execute(sql, params)
    rows = cur.fetchall()
    conn.close()
    return _marcar_ultimas([dict(r) for r in rows])


def versiones_con_anexo(codigo_base, tipo):
    if not codigo_base:
        return []
    versiones = versiones_de_familia(codigo_base, tipo=tipo)
    resultado = []
    for v in versiones:
        try:
            datos = json.loads(v.get("datos_json") or "{}")
        except Exception:
            datos = {}
        fecha = datos.get("fecha_revision", "") or "0000-00-00"
        try:
            rev_num = int(v.get("revision") or 0)
        except Exception:
            rev_num = 0
        resultado.append({
            "id":              v["id"],
            "codigo_completo": v["codigo_completo"],
            "variante":        v["variante"],
            "revision":        f"{v['revision']:02d}",
            "revision_num":    rev_num,
            "fecha_revision":  fecha,
            "anexo":           datos.get("anexo_detalle_cambios", "") or "—",
        })
    resultado.sort(key=lambda x: (x["revision_num"], x["fecha_revision"]))
    return resultado


def eliminar_publicado(id_esp):
    esp = obtener(id_esp)
    if not esp:
        return None
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("DELETE FROM especificaciones_generadas WHERE id = ?", (id_esp,))
    conn.commit()
    conn.close()
    return esp


def bump_drafts_after_publish(codigo_base, variante, tipo, revision):
    """Si hay un borrador de la misma familia con revision >= revision,
    lo empuja hasta encontrar un hueco libre."""
    cb = codigo_base.strip().upper()
    va = (variante or "").strip().upper()
    conn = get_db_connection()
    cur = conn.cursor()

    cur.execute("""
        SELECT id, revision FROM borradores
        WHERE codigo_base = ? AND variante = ? AND tipo = ?
    """, (cb, va, tipo))
    row = cur.fetchone()
    if not row:
        conn.close(); return
    draft_id, draft_rev = row["id"], row["revision"]

    if draft_rev < revision:
        conn.close(); return

    nueva = draft_rev + 1
    while True:
        cur.execute("""
            SELECT 1 FROM especificaciones_generadas
              WHERE codigo_base=? AND variante=? AND tipo=? AND revision=?
            UNION ALL
            SELECT 1 FROM borradores
              WHERE codigo_base=? AND variante=? AND tipo=? AND revision=? AND id!=?
            LIMIT 1
        """, (cb, va, tipo, nueva, cb, va, tipo, nueva, draft_id))
        if cur.fetchone() is None:
            break
        nueva += 1

    cur.execute("""
        UPDATE borradores SET revision = ?, fecha_actualizacion = ?
         WHERE id = ?
    """, (nueva, datetime.now().strftime("%Y-%m-%d %H:%M:%S"), draft_id))
    conn.commit()
    conn.close()


# ─── Borradores ───
def contar_borradores(id_usuario):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM borradores WHERE id_usuario = ?", (id_usuario,))
    n = cur.fetchone()[0]
    conn.close()
    return n


def obtener_borrador(id_b):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM borradores WHERE id = ?", (id_b,))
    row = cur.fetchone()
    conn.close()
    return dict(row) if row else None


def obtener_borrador_de_familia(codigo_base, variante, tipo):
    cb = codigo_base.strip().upper()
    va = (variante or "").strip().upper()
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("""
        SELECT * FROM borradores
        WHERE codigo_base = ? AND variante = ? AND tipo = ?
        LIMIT 1
    """, (cb, va, tipo))
    row = cur.fetchone()
    conn.close()
    return dict(row) if row else None


def listar_borradores_usuario(id_usuario):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("""
        SELECT * FROM borradores
        WHERE id_usuario = ?
        ORDER BY fecha_actualizacion DESC
    """, (id_usuario,))
    rows = cur.fetchall()
    conn.close()
    return [dict(r) for r in rows]


def crear_borrador(*, id_usuario, usuario_nombre, tipo, codigo_base, variante,
                  revision, titulo, cliente, producto, datos):
    cb = codigo_base.strip().upper()
    va = (variante or "").strip().upper()
    cc = codigo_completo(cb, va)
    ahora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO borradores
            (id_usuario, usuario_nombre, tipo, codigo_base, variante, revision,
             codigo_completo, titulo, cliente, producto, datos_json,
             fecha_creacion, fecha_actualizacion)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
    """, (id_usuario, usuario_nombre, tipo, cb, va, revision, cc,
          titulo, cliente, producto, json.dumps(datos, ensure_ascii=False),
          ahora, ahora))
    new_id = cur.lastrowid
    conn.commit()
    conn.close()
    return new_id


def actualizar_borrador(id_b, *, titulo, cliente, producto, datos):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("""
        UPDATE borradores
           SET titulo = ?, cliente = ?, producto = ?, datos_json = ?,
               fecha_actualizacion = ?
         WHERE id = ?
    """, (titulo, cliente, producto, json.dumps(datos, ensure_ascii=False),
          datetime.now().strftime("%Y-%m-%d %H:%M:%S"), id_b))
    conn.commit()
    conn.close()


def eliminar_borrador(id_b):
    b = obtener_borrador(id_b)
    if not b:
        return None
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("DELETE FROM borradores WHERE id = ?", (id_b,))
    conn.commit()
    conn.close()
    return b


def publicar_borrador(id_b, nombre_descarga=None):
    """Transfiere datos del borrador a publicados, borra el borrador."""
    b = obtener_borrador(id_b)
    if not b:
        return None

    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO especificaciones_generadas
            (id_usuario, usuario_nombre, tipo, codigo_base, variante, revision,
             codigo_completo, titulo, cliente, producto, nombre_descarga,
             datos_json, fecha_generacion)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
    """, (b["id_usuario"], b["usuario_nombre"], b["tipo"],
          b["codigo_base"], b["variante"], b["revision"], b["codigo_completo"],
          b["titulo"], b["cliente"], b["producto"], nombre_descarga,
          b["datos_json"], datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
    new_id = cur.lastrowid
    cur.execute("DELETE FROM borradores WHERE id = ?", (id_b,))
    conn.commit()
    conn.close()
    return new_id

# ═══════════════════════════════════════════════
# PERMISOS
# ═══════════════════════════════════════════════

def usuarios_con_acceso_seccion(seccion="especificaciones"):
    """Devuelve los usuarios que tienen permiso explícito para esa sección."""
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("""
        SELECT u.id, u.nombre
          FROM usuarios u
          JOIN permisos_usuario_seccion p ON p.id_usuario = u.id
         WHERE u.activo = 1 AND p.seccion = ?
         ORDER BY u.nombre
    """, (seccion,))
    rows = cur.fetchall()
    conn.close()
    return [dict(r) for r in rows]


def obtener_permisos_globales(id_dueno):
    """Devuelve la lista de permisos globales otorgados por el dueño."""
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("""
        SELECT p.*, u.nombre AS usuario_nombre
          FROM permisos_globales p
          JOIN usuarios u ON u.id = p.id_usuario
         WHERE p.id_dueno = ?
         ORDER BY u.nombre
    """, (id_dueno,))
    rows = cur.fetchall()
    conn.close()
    return [dict(r) for r in rows]


def set_permisos_globales(id_dueno, permisos: list[dict]):
    """
    Reemplaza la lista de permisos globales del dueño.
    permisos = [{'id_usuario': 5, 'puede_editar': 1, 'puede_publicar': 0, 'puede_eliminar': 0}, ...]
    """
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("DELETE FROM permisos_globales WHERE id_dueno = ?", (id_dueno,))
    for p in permisos:
        cur.execute("""
            INSERT INTO permisos_globales
                (id_dueno, id_usuario, puede_editar, puede_publicar, puede_eliminar)
            VALUES (?, ?, ?, ?, ?)
        """, (id_dueno, int(p["id_usuario"]),
              int(p.get("puede_editar",   1)),
              int(p.get("puede_publicar", 0)),
              int(p.get("puede_eliminar", 0))))
    conn.commit()
    conn.close()


def obtener_permisos_especificos(id_borrador):
    """Devuelve overrides para un borrador puntual."""
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("""
        SELECT p.*, u.nombre AS usuario_nombre
          FROM permisos_especificos p
          JOIN usuarios u ON u.id = p.id_usuario
         WHERE p.id_borrador = ?
         ORDER BY u.nombre
    """, (id_borrador,))
    rows = cur.fetchall()
    conn.close()
    return [dict(r) for r in rows]


def set_permisos_especificos(id_borrador, permisos: list[dict]):
    """Reemplaza los overrides de un borrador puntual."""
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("DELETE FROM permisos_especificos WHERE id_borrador = ?", (id_borrador,))
    for p in permisos:
        cur.execute("""
            INSERT INTO permisos_especificos
                (id_borrador, id_usuario, puede_editar, puede_publicar, puede_eliminar)
            VALUES (?, ?, ?, ?, ?)
        """, (id_borrador, int(p["id_usuario"]),
              int(p.get("puede_editar",   0)),
              int(p.get("puede_publicar", 0)),
              int(p.get("puede_eliminar", 0))))
    conn.commit()
    conn.close()


def calcular_permisos_borrador(id_borrador, id_usuario, es_admin=False):
    """
    Devuelve dict con los permisos efectivos del usuario sobre el borrador.
    Aplica override: específico > global.
    """
    b = obtener_borrador(id_borrador)
    if not b:
        return None

    # Dueño
    if b["id_usuario"] == id_usuario:
        return {"puede_ver": True, "puede_editar": True,
                "puede_publicar": True, "puede_eliminar": True, "es_dueno": True}

    # Admin
    if es_admin:
        return {"puede_ver": True, "puede_editar": True,
                "puede_publicar": True, "puede_eliminar": True, "es_dueno": False}

    conn = get_db_connection()
    cur = conn.cursor()

    # ¿Tiene override específico?
    cur.execute("""
        SELECT puede_editar, puede_publicar, puede_eliminar
          FROM permisos_especificos
         WHERE id_borrador = ? AND id_usuario = ?
    """, (id_borrador, id_usuario))
    esp = cur.fetchone()

    if esp:
        conn.close()
        return {"puede_ver": True,
                "puede_editar":    bool(esp["puede_editar"]),
                "puede_publicar":  bool(esp["puede_publicar"]),
                "puede_eliminar":  bool(esp["puede_eliminar"]),
                "es_dueno": False}

    # ¿Tiene permiso global?
    cur.execute("""
        SELECT puede_editar, puede_publicar, puede_eliminar
          FROM permisos_globales
         WHERE id_dueno = ? AND id_usuario = ?
    """, (b["id_usuario"], id_usuario))
    glob = cur.fetchone()
    conn.close()

    if glob:
        return {"puede_ver": True,
                "puede_editar":    bool(glob["puede_editar"]),
                "puede_publicar":  bool(glob["puede_publicar"]),
                "puede_eliminar":  bool(glob["puede_eliminar"]),
                "es_dueno": False}

    return {"puede_ver": False, "puede_editar": False,
            "puede_publicar": False, "puede_eliminar": False, "es_dueno": False}


def borradores_compartidos_conmigo(id_usuario, es_admin=False):
    """
    Devuelve la lista de borradores de OTROS usuarios a los que este usuario tiene acceso.
    """
    conn = get_db_connection()
    cur = conn.cursor()
    if es_admin:
        cur.execute("""
            SELECT b.*, u.nombre AS dueno_nombre
              FROM borradores b
              JOIN usuarios u ON u.id = b.id_usuario
             WHERE b.id_usuario != ?
             ORDER BY b.fecha_actualizacion DESC
        """, (id_usuario,))
    else:
        cur.execute("""
            SELECT DISTINCT b.*, u.nombre AS dueno_nombre
              FROM borradores b
              JOIN usuarios u ON u.id = b.id_usuario
             WHERE b.id_usuario != ?
               AND (
                    b.id IN (
                        SELECT id_borrador FROM permisos_especificos
                         WHERE id_usuario = ?
                    )
                    OR b.id_usuario IN (
                        SELECT id_dueno FROM permisos_globales
                         WHERE id_usuario = ?
                    )
               )
             ORDER BY b.fecha_actualizacion DESC
        """, (id_usuario, id_usuario, id_usuario))
    rows = cur.fetchall()
    conn.close()
    return [dict(r) for r in rows]


# ═══════════════════════════════════════════════
# NOTIFICACIONES
# ═══════════════════════════════════════════════

def crear_notificacion(id_usuario, mensaje, url=None):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO notificaciones (id_usuario, mensaje, url)
        VALUES (?, ?, ?)
    """, (id_usuario, mensaje, url))
    conn.commit()
    conn.close()


def notificaciones_no_leidas(id_usuario):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("""
        SELECT * FROM notificaciones
         WHERE id_usuario = ? AND leida = 0
         ORDER BY fecha DESC
         LIMIT 20
    """, (id_usuario,))
    rows = cur.fetchall()
    conn.close()
    return [dict(r) for r in rows]


def marcar_notificaciones_leidas(id_usuario, ids: list[int] | None = None):
    conn = get_db_connection()
    cur = conn.cursor()
    if ids:
        placeholders = ",".join("?" * len(ids))
        cur.execute(f"""
            UPDATE notificaciones SET leida = 1
             WHERE id_usuario = ? AND id IN ({placeholders})
        """, [id_usuario] + list(ids))
    else:
        cur.execute("UPDATE notificaciones SET leida = 1 WHERE id_usuario = ?", (id_usuario,))
    conn.commit()
    conn.close()


# ═══════════════════════════════════════════════
# EDICIÓN ACTIVA (bloqueo optimista - Fase 3)
# ═══════════════════════════════════════════════

def marcar_edicion_activa(id_borrador, id_usuario):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO borrador_edicion_activa (id_borrador, id_usuario, ultima_actividad)
        VALUES (?, ?, datetime('now'))
        ON CONFLICT(id_borrador) DO UPDATE
            SET id_usuario = excluded.id_usuario,
                ultima_actividad = excluded.ultima_actividad
    """, (id_borrador, id_usuario))
    conn.commit()
    conn.close()


def quien_esta_editando(id_borrador, id_usuario_actual=None, minutos=5):
    """Devuelve el nombre del otro usuario que está editando (si hay), o None."""
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("""
        SELECT e.id_usuario, u.nombre
          FROM borrador_edicion_activa e
          JOIN usuarios u ON u.id = e.id_usuario
         WHERE e.id_borrador = ?
           AND e.ultima_actividad >= datetime('now', ?)
    """, (id_borrador, f"-{minutos} minutes"))
    row = cur.fetchone()
    conn.close()
    if not row:
        return None
    if id_usuario_actual and row["id_usuario"] == id_usuario_actual:
        return None
    return row["nombre"]


def limpiar_edicion_activa(id_borrador, id_usuario):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("""
        DELETE FROM borrador_edicion_activa
         WHERE id_borrador = ? AND id_usuario = ?
    """, (id_borrador, id_usuario))
    conn.commit()
    conn.close()

def borrador_cambio_desde(id_b, fecha_actualizacion_original):
    """
    Devuelve True si el borrador cambió desde esa fecha (o si ya no existe).
    Usado para bloqueo optimista.
    """
    if not fecha_actualizacion_original:
        return False
    b = obtener_borrador(id_b)
    if not b:
        return True
    return b["fecha_actualizacion"] != fecha_actualizacion_original


# ─── Usuarios (email) ───
def obtener_usuario(id_usuario):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM usuarios WHERE id = ?", (id_usuario,))
    row = cur.fetchone()
    conn.close()
    return dict(row) if row else None


def actualizar_email_usuario(id_usuario, email):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("UPDATE usuarios SET email = ? WHERE id = ?", (email, id_usuario))
    conn.commit()
    conn.close()


# ─── Contactos (autocompletado) ───
def buscar_contactos(q, limite=10):
    q = (q or "").strip()
    if not q:
        return []
    conn = get_db_connection()
    cur = conn.cursor()
    like = f"%{q}%"
    cur.execute("""
        SELECT email, nombre, total_envios, ultimo_uso
          FROM contactos_correo
         WHERE email LIKE ? OR COALESCE(nombre, '') LIKE ?
         ORDER BY total_envios DESC, ultimo_uso DESC
         LIMIT ?
    """, (like, like, limite))
    rows = cur.fetchall()
    conn.close()
    return [dict(r) for r in rows]


def registrar_contacto(email, nombre=None):
    email = (email or "").strip().lower()
    if not email:
        return
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO contactos_correo (email, nombre, total_envios, ultimo_uso)
        VALUES (?, ?, 1, datetime('now','localtime'))
        ON CONFLICT(email) DO UPDATE SET
            nombre       = COALESCE(?, contactos_correo.nombre),
            total_envios = contactos_correo.total_envios + 1,
            ultimo_uso   = datetime('now','localtime')
    """, (email, nombre, nombre))
    conn.commit()
    conn.close()


# ─── Envíos (cola + auditoría) ───
def crear_envio(id_esp, id_usuario, destinatario, remitente, asunto, cuerpo=""):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO envios_correo
            (id_esp, id_usuario, destinatario, remitente, asunto, cuerpo, estado)
        VALUES (?, ?, ?, ?, ?, ?, 'pendiente')
    """, (id_esp, id_usuario, destinatario, remitente, asunto, cuerpo))
    new_id = cur.lastrowid
    conn.commit()
    conn.close()
    return new_id


def obtener_envio(id_envio):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM envios_correo WHERE id = ?", (id_envio,))
    row = cur.fetchone()
    conn.close()
    return dict(row) if row else None


def marcar_envio_enviando(id_envio):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("""
        UPDATE envios_correo
           SET estado = 'enviando',
               fecha_inicio = datetime('now','localtime'),
               intentos = intentos + 1
         WHERE id = ?
    """, (id_envio,))
    conn.commit()
    conn.close()


def marcar_envio_enviado(id_envio):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("""
        UPDATE envios_correo
           SET estado = 'enviado',
               fecha_envio = datetime('now','localtime'),
               error = NULL
         WHERE id = ?
    """, (id_envio,))
    conn.commit()
    conn.close()


def marcar_envio_error(id_envio, error):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("""
        UPDATE envios_correo
           SET estado = 'error', error = ?
         WHERE id = ?
    """, (error, id_envio))
    conn.commit()
    conn.close()


def envios_pendientes():
    """Huérfanos al iniciar: pendientes o que quedaron 'enviando' por un crash."""
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("""
        SELECT * FROM envios_correo
         WHERE estado IN ('pendiente', 'enviando')
         ORDER BY id ASC
    """)
    rows = cur.fetchall()
    conn.close()
    return [dict(r) for r in rows]