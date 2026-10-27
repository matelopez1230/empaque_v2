# migracion_correo.py
"""
Agrega:
  - columna 'email' a usuarios (derivada de nombre@chocolatesmapsa.com)
  - tabla contactos_correo (autocompletado de destinatarios)
  - tabla envios_correo (banco de envíos + auditoría)
Idempotente.
"""
from pathlib import Path
import sqlite3

BASE = Path(__file__).resolve().parent
DB_PATH = BASE / "instance" / "especificaciones.db"

if not DB_PATH.exists():
    print(f"❌ No existe la DB en {DB_PATH}")
    raise SystemExit(1)

conn = sqlite3.connect(DB_PATH)
conn.row_factory = sqlite3.Row
cur = conn.cursor()

# ── 1) columna email en usuarios ──
cols = [r[1] for r in cur.execute("PRAGMA table_info(usuarios)").fetchall()]
if "email" not in cols:
    cur.execute("ALTER TABLE usuarios ADD COLUMN email TEXT")
    print("✅ Columna 'email' agregada a usuarios")
else:
    print("ℹ️  Columna 'email' ya existe")

# Seed: derivar email para usuarios sin email
cur.execute("SELECT id, nombre FROM usuarios WHERE email IS NULL OR email = ''")
faltan = cur.fetchall()
if faltan:
    for r in faltan:
        email = f"{r['nombre']}@chocolatesmapsa.com".lower()
        cur.execute("UPDATE usuarios SET email = ? WHERE id = ?", (email, r["id"]))
    print(f"✅ {len(faltan)} emails derivados de nombre@chocolatesmapsa.com")

# ── 2) tablas nuevas ──
cur.executescript("""
CREATE TABLE IF NOT EXISTS contactos_correo (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    email         TEXT NOT NULL UNIQUE,
    nombre        TEXT,
    total_envios  INTEGER NOT NULL DEFAULT 0,
    fecha_alta    TEXT NOT NULL DEFAULT (datetime('now','localtime')),
    ultimo_uso    TEXT
);

CREATE TABLE IF NOT EXISTS envios_correo (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    id_esp         INTEGER NOT NULL,
    id_usuario     INTEGER NOT NULL,
    destinatario   TEXT NOT NULL,
    remitente      TEXT NOT NULL,
    asunto         TEXT,
    cuerpo         TEXT,
    estado         TEXT NOT NULL DEFAULT 'pendiente',
    error          TEXT,
    intentos       INTEGER NOT NULL DEFAULT 0,
    fecha_creacion TEXT NOT NULL DEFAULT (datetime('now','localtime')),
    fecha_inicio   TEXT,
    fecha_envio    TEXT
);

CREATE INDEX IF NOT EXISTS idx_envios_estado   ON envios_correo(estado);
CREATE INDEX IF NOT EXISTS idx_envios_esp      ON envios_correo(id_esp);
CREATE INDEX IF NOT EXISTS idx_envios_fecha    ON envios_correo(fecha_creacion DESC);
CREATE INDEX IF NOT EXISTS idx_contactos_email ON contactos_correo(email);
""")

conn.commit()
conn.close()
print("✅ Tablas de correo listas")