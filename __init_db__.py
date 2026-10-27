# init_db.py
"""
Inicializa la base de datos y crea el usuario admin.
Uso:  python init_db.py
"""
from werkzeug.security import generate_password_hash
from db import get_db_connection


DDL = """
CREATE TABLE IF NOT EXISTS usuarios (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    nombre        TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    activo        INTEGER NOT NULL DEFAULT 1,
    es_admin      INTEGER NOT NULL DEFAULT 0,
    fecha_alta    TEXT NOT NULL DEFAULT (datetime('now','localtime'))
);

CREATE TABLE IF NOT EXISTS especificaciones_generadas (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    id_usuario        INTEGER NOT NULL,
    usuario_nombre    TEXT NOT NULL,
    tipo              TEXT NOT NULL,
    codigo_base       TEXT NOT NULL,
    variante          TEXT NOT NULL DEFAULT '',
    revision          INTEGER NOT NULL DEFAULT 0,
    codigo_completo   TEXT NOT NULL,
    titulo            TEXT,
    cliente           TEXT,
    producto          TEXT,
    archivo_pdf       TEXT NOT NULL,
    datos_json        TEXT NOT NULL,
    fecha_generacion  TEXT NOT NULL,
    tamano_bytes      INTEGER,
    FOREIGN KEY (id_usuario) REFERENCES usuarios(id)
);

CREATE INDEX IF NOT EXISTS idx_codigo_base
    ON especificaciones_generadas(codigo_base);
CREATE INDEX IF NOT EXISTS idx_usuario
    ON especificaciones_generadas(id_usuario);
"""


def inicializar():
    conn = get_db_connection()
    cur = conn.cursor()
    cur.executescript(DDL)

    # Crear admin si no existe
    cur.execute("SELECT id FROM usuarios WHERE nombre = 'admin'")
    if not cur.fetchone():
        cur.execute("""
            INSERT INTO usuarios (nombre, password_hash, activo, es_admin)
            VALUES (?, ?, 1, 1)
        """, ("admin", generate_password_hash("admin123")))
        print("✅ Usuario 'admin' creado (contraseña: admin123)")
    else:
        print("ℹ️  Usuario 'admin' ya existe")

    conn.commit()
    conn.close()
    print("✅ Base de datos lista")


if __name__ == "__main__":
    inicializar()