#!/usr/bin/env python3
"""
exportar_sqlite_a_csv.py

Convierte tablas de una base de datos SQLite (.db / .sqlite / .sqlite3)
a archivos CSV para su importación en otras herramientas.

Uso:
    # Exportar TODAS las tablas a la carpeta ./csv_export
    python exportar_sqlite_a_csv.py mi_base.db

    # Exportar una tabla específica
    python exportar_sqlite_a_csv.py mi_base.db --tabla clientes

    # Con opciones personalizadas
    python exportar_sqlite_a_csv.py mi_base.db --tabla ventas \
        --salida ./exports --delimitador ";" --encoding utf-8-sig

Opciones:
    --tabla        Nombre de la tabla a exportar (si se omite, exporta todas)
    --salida       Carpeta de destino (por defecto: ./csv_export)
    --delimitador  Separador de columnas (por defecto: ",")
    --encoding     Codificación del archivo (por defecto: utf-8-sig,
                   compatible con Excel)
"""

import argparse
import csv
import os
import sqlite3
import sys


def listar_tablas(conn):
    """Devuelve la lista de tablas de usuario (excluye las internas)."""
    cur = conn.cursor()
    cur.execute("""
        SELECT name FROM sqlite_master
        WHERE type='table' AND name NOT LIKE 'sqlite_%'
        ORDER BY name;
    """)
    return [fila[0] for fila in cur.fetchall()]


def exportar_tabla(conn, tabla, ruta_csv, delimitador=",", encoding="utf-8-sig"):
    """Exporta una tabla completa a un archivo CSV."""
    cur = conn.cursor()
    # Comillas dobles por si el nombre tiene espacios o caracteres raros
    cur.execute(f'SELECT * FROM "{tabla}"')

    columnas = [desc[0] for desc in cur.description]
    filas = cur.fetchall()

    with open(ruta_csv, "w", newline="", encoding=encoding) as f:
        writer = csv.writer(
            f,
            delimiter=delimitador,
            quoting=csv.QUOTE_MINIMAL,
            lineterminator="\n",
        )
        writer.writerow(columnas)
        writer.writerows(filas)

    return len(columnas), len(filas)


def main():
    parser = argparse.ArgumentParser(
        description="Exporta tablas de una base SQLite a archivos CSV."
    )
    parser.add_argument("db", help="Ruta al archivo .db / .sqlite3")
    parser.add_argument("--tabla", help="Tabla específica a exportar")
    parser.add_argument(
        "--salida",
        default="csv_export",
        help="Carpeta de salida (por defecto: ./csv_export)",
    )
    parser.add_argument(
        "--delimitador", default=",", help='Separador de columnas (por defecto ",")'
    )
    parser.add_argument(
        "--encoding", default="utf-8-sig", help="Codificación (por defecto utf-8-sig)"
    )
    args = parser.parse_args()

    if not os.path.isfile(args.db):
        print(f"❌ No existe el archivo: {args.db}", file=sys.stderr)
        sys.exit(1)

    os.makedirs(args.salida, exist_ok=True)

    conn = sqlite3.connect(args.db)
    try:
        if args.tabla:
            tablas = [args.tabla]
        else:
            tablas = listar_tablas(conn)

        if not tablas:
            print("⚠️  La base de datos no tiene tablas para exportar.")
            return

        print(f"📦 Base de datos: {args.db}")
        print(f"📁 Carpeta de salida: {os.path.abspath(args.salida)}\n")

        for tabla in tablas:
            ruta = os.path.join(args.salida, f"{tabla}.csv")
            try:
                n_cols, n_filas = exportar_tabla(
                    conn, tabla, ruta, args.delimitador, args.encoding
                )
                print(
                    f"  ✔ {tabla:<25} -> {os.path.basename(ruta)}  "
                    f"({n_filas} filas, {n_cols} columnas)"
                )
            except sqlite3.Error as e:
                print(f"  ✘ {tabla}: error -> {e}", file=sys.stderr)

    finally:
        conn.close()

    print("\n✅ Exportación completada.")


if __name__ == "__main__":
    main()