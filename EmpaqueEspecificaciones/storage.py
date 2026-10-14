# storage.py
import json
import re
import uuid
from datetime import datetime
from pathlib import Path
from db import get_db_connection

BASE_DIR    = Path(__file__).resolve().parent
STORAGE_DIR = BASE_DIR / "storage"


_SANITIZE = re.compile(r"[^A-Za-z0-9_\-]")


def _sanitizar(texto: str) -> str:
    return _SANITIZE.sub("_", texto or "").strip("_") or "SIN_CODIGO"


def codigo_completo(codigo_base: str, variante: str) -> str:
    return f"{codigo_base.strip().upper()}{variante.strip().upper()}"


def siguiente_revision(codigo_base: str, variante: str) -> int:
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("""
        SELECT MAX(revision) AS max_rev
        FROM especificaciones_generadas
        WHERE codigo_base = ? AND variante = ?
    """, (codigo_base.upper(), variante.upper()))
    row = cur.fetchone()
    conn.close()
    max_rev = row["max_rev"] if row and row["max_rev"] is not None else -1
    return max_rev + 1


def guardar_especificacion(*, id_usuario, usuario_nombre, tipo,
                           codigo_base, variante, revision,
                           titulo, cliente, producto,
                           datos: dict, pdf_bytes: bytes) -> int:
    codigo_base = codigo_base.strip().upper()
    variante    = variante.strip().upper()
    base_san    = _sanitizar(codigo_base)
    carpeta     = STORAGE_DIR / base_san
    carpeta.mkdir(parents=True, exist_ok=True)

    sufijo = uuid.uuid4().hex[:8]
    nombre_archivo = f"{base_san}{variante}_{tipo}_rev{revision:02d}_{sufijo}.pdf"
    ruta_abs       = carpeta / nombre_archivo
    ruta_rel       = f"{base_san}/{nombre_archivo}"

    ruta_abs.write_bytes(pdf_bytes)

    cod_completo = codigo_completo(codigo_base, variante)

    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO especificaciones_generadas
            (id_usuario, usuario_nombre, tipo,
             codigo_base, variante, revision, codigo_completo,
             titulo, cliente, producto,
             archivo_pdf, datos_json, fecha_generacion, tamano_bytes)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)
    """, (
        id_usuario, usuario_nombre, tipo,
        codigo_base, variante, revision, cod_completo,
        titulo, cliente, producto,
        ruta_rel,
        json.dumps(datos, ensure_ascii=False),
        datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        len(pdf_bytes),
    ))
    new_id = cur.lastrowid
    conn.commit()
    conn.close()
    return new_id


def obtener(id_esp: int) -> dict | None:
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM especificaciones_generadas WHERE id = ?", (id_esp,))
    row = cur.fetchone()
    conn.close()
    return dict(row) if row else None


def ruta_absoluta(esp: dict) -> Path:
    return STORAGE_DIR / esp["archivo_pdf"]


def versiones_de_familia(codigo_base: str) -> list[dict]:
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("""
        SELECT * FROM especificaciones_generadas
        WHERE codigo_base = ?
        ORDER BY variante ASC, revision DESC
    """, (codigo_base.upper(),))
    rows = cur.fetchall()
    conn.close()
    return [dict(r) for r in rows]


def ultimas_generadas(limite: int = 15, id_usuario: int | None = None) -> list[dict]:
    conn = get_db_connection()
    cur = conn.cursor()
    if id_usuario is not None:
        cur.execute("""
            SELECT * FROM especificaciones_generadas
            WHERE id_usuario = ?
            ORDER BY id DESC LIMIT ?
        """, (id_usuario, limite))
    else:
        cur.execute("""
            SELECT * FROM especificaciones_generadas
            ORDER BY id DESC LIMIT ?
        """, (limite,))
    rows = cur.fetchall()
    conn.close()
    return [dict(r) for r in rows]

def buscar_especificaciones(tipo: str | None = None,
                             q: str = "",
                             limite: int = 100) -> list[dict]:
    """
    Busca por código base, código completo, cliente, producto o título.
    Si tipo es None, busca en todos los tipos.
    """
    conn = get_db_connection()
    cur = conn.cursor()
    sql = "SELECT * FROM especificaciones_generadas WHERE 1=1"
    params = []
    if tipo:
        sql += " AND tipo = ?"
        params.append(tipo)
    if q:
        sql += """ AND (
            codigo_base       LIKE ? OR
            codigo_completo   LIKE ? OR
            cliente           LIKE ? OR
            producto          LIKE ? OR
            titulo            LIKE ?
        )"""
        like = f"%{q}%"
        params.extend([like] * 5)
    sql += " ORDER BY id DESC LIMIT ?"
    params.append(limite)
    cur.execute(sql, params)
    rows = cur.fetchall()
    conn.close()
    return [dict(r) for r in rows]

def versiones_con_anexo(codigo_base: str) -> list[dict]:
    """
    Devuelve todas las versiones del código base (excepto la actual),
    ordenadas por fecha ascendente (más vieja primero).
    """
    if not codigo_base:
        return []

    versiones = versiones_de_familia(codigo_base)

    # Parsear datos y ordenar por fecha ascendente
    resultado = []
    for v in versiones:
        try:
            datos = json.loads(v.get('datos_json') or '{}')
        except Exception:
            datos = {}

        fecha = datos.get('fecha_revision', '') or '0000-00-00'

        resultado.append({
            'id':              v['id'],
            'codigo_completo': v['codigo_completo'],
            'variante':        v['variante'],
            'revision':        f"{v['revision']:02d}",
            'fecha_revision':  fecha,
            'anexo':           datos.get('anexo_detalle_cambios', '') or '—',
        })

    # Ordenar por fecha (string ISO funciona)
    resultado.sort(key=lambda x: x['fecha_revision'])
    return resultado