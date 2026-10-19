# migracion_permisos.py
"""
Agrega las tablas del sistema de permisos y de notificaciones.
Idempotente: si las tablas ya existen, no las recrea.
"""
from pathlib import Path
import sqlite3

BASE     = Path(__file__).resolve().parent
DB_PATH  = BASE / "instance" / "especificaciones.db"

if not DB_PATH.exists():
    print(f"❌ No existe la DB en {DB_PATH}")
    raise SystemExit(1)

conn = sqlite3.connect(DB_PATH)
cur  = conn.cursor()

cur.executescript("""
CREATE TABLE IF NOT EXISTS permisos_globales (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    id_dueno INTEGER NOT NULL,
    id_usuario INTEGER NOT NULL,
    puede_editar INTEGER DEFAULT 1,
    puede_publicar INTEGER DEFAULT 0,
    puede_eliminar INTEGER DEFAULT 0,
    fecha_otorgado TEXT DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(id_dueno, id_usuario)
);

CREATE TABLE IF NOT EXISTS permisos_especificos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    id_borrador INTEGER NOT NULL,
    id_usuario INTEGER NOT NULL,
    puede_editar INTEGER DEFAULT 0,
    puede_publicar INTEGER DEFAULT 0,
    puede_eliminar INTEGER DEFAULT 0,
    fecha_otorgado TEXT DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(id_borrador, id_usuario)
);

CREATE TABLE IF NOT EXISTS borrador_edicion_activa (
    id_borrador INTEGER PRIMARY KEY,
    id_usuario INTEGER NOT NULL,
    ultima_actividad TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS notificaciones (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    id_usuario INTEGER NOT NULL,
    mensaje TEXT NOT NULL,
    url TEXT,
    leida INTEGER DEFAULT 0,
    fecha TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS permisos_usuario_seccion (
    id_usuario INTEGER NOT NULL,
    seccion TEXT NOT NULL,
    PRIMARY KEY (id_usuario, seccion)
);

CREATE INDEX IF NOT EXISTS idx_perm_glob_dueno ON permisos_globales(id_dueno);
CREATE INDEX IF NOT EXISTS idx_perm_esp_borr  ON permisos_especificos(id_borrador);
CREATE INDEX IF NOT EXISTS idx_notif_usuario  ON notificaciones(id_usuario, leida);
""")

# Seed: todos los usuarios activos tienen acceso a la sección "especificaciones"
cur.execute("SELECT id FROM usuarios WHERE activo = 1")
for (uid,) in cur.fetchall():
    cur.execute("""
        INSERT OR IGNORE INTO permisos_usuario_seccion (id_usuario, seccion)
        VALUES (?, 'especificaciones')
    """, (uid,))

conn.commit()
conn.close()
print("✅ Tablas de permisos y notificaciones creadas")
print("✅ Usuarios existentes con acceso a la sección 'especificaciones'")