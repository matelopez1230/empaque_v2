import sqlite3

DB = "especificaciones.db"
con = sqlite3.connect(DB)
con.row_factory = sqlite3.Row

print("=== TABLAS Y VISTAS ===")
for r in con.execute("SELECT type, name FROM sqlite_master WHERE type IN ('table','view') ORDER BY type, name"):
    print(f"{r['type']:6} {r['name']}")

print("\n=== DDL (CREATE TABLE / INDEX / VIEW / TRIGGER) ===")
for r in con.execute("SELECT sql FROM sqlite_master WHERE sql IS NOT NULL ORDER BY type, name"):
    print(r['sql'] + ";\n")

print("\n=== FOREIGN KEYS ===")
for r in con.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"):
    tbl = r['name']
    for fk in con.execute(f'PRAGMA foreign_key_list("{tbl}")'):
        print(f"{tbl}.{fk['from']} -> {fk['table']}.{fk['to']}  (on_update={fk['on_update']}, on_delete={fk['on_delete']})")

print("\n=== ÍNDICES ===")
for r in con.execute("SELECT name, tbl_name, sql FROM sqlite_master WHERE type='index' ORDER BY tbl_name, name"):
    print(f"{r['tbl_name']}: {r['name']}  ->  {r['sql']}")

con.close()
