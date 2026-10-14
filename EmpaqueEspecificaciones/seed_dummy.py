# seed_dummy.py
"""
Carga especificaciones dummy para pruebas.
Uso:  python seed_dummy.py
      python seed_dummy.py --reset    (borra los dummies previos y los recrea)

Es seguro correrlo varias veces: detecta duplicados y los omite.
"""
import sys
from datetime import datetime
from app import app
from pdf_utils import generar_pdf, logo_base64
import storage
from db import get_db_connection


TIPOS = {
    "diseno_grafico":   "Diseño Gráfico",
    "material_empaque": "Material de Empaque",
    "etiqueta":         "Etiqueta",
    "etiqueta_zebra":   "Etiqueta Zebra",
}


DUMMIES = [
    # ─────────────────────────────────────────────
    # CAJ03A — Diseño Gráfico
    # ─────────────────────────────────────────────
    {
        "tipo": "diseno_grafico",
        "codigo_base": "CAJ03",
        "variante": "A",
        "revision": 0,
        "cliente": "Distribuidora del Sur S.A.",
        "producto": "Caja plegadiza cartón corrugado 40x30x25 cm",
        "titulo": "Diseño gráfico caja CAJ03A",
        "observaciones": (
            "Diseño a 4 colores (CMYK) + barniz sectorizado sobre el logo.\n"
            "Frente: logo cliente centrado (80 mm de ancho) + claim de marca.\n"
            "Laterales: información nutricional y código de barras EAN-13.\n"
            "Dorso: instrucciones de armado y datos del fabricante.\n"
            "Tipografía: Arial Bold para títulos, Arial Regular para cuerpo.\n"
            "Trazo de corte: 1 pt magenta (línea de corte).\n"
            "Trazo de doblez: 1 pt cian (línea de plegado).\n"
            "Sangrado: 3 mm en todos los bordes."
        ),
    },
    # ─────────────────────────────────────────────
    # CAJ03A — Material de Empaque
    # ─────────────────────────────────────────────
    {
        "tipo": "material_empaque",
        "codigo_base": "CAJ03",
        "variante": "A",
        "revision": 0,
        "cliente": "Distribuidora del Sur S.A.",
        "producto": "Caja plegadiza cartón corrugado 40x30x25 cm",
        "titulo": "Especificación material caja CAJ03A",
        "observaciones": (
            "Estructura: cartón corrugado doble pared, tipo BC.\n"
            "Gramaje liner exterior: 440 g/m².\n"
            "Gramaje liner interior: 150 g/m².\n"
            "Resistencia al aplastamiento (BCT): mínimo 12 kN/m.\n"
            "Resistencia a la humedad: 85% HR durante 48 hs sin deformación.\n"
            "Fuelle: pegado lateral con adhesivo hot-melt.\n"
            "Certificación: FSC obligatoria.\n"
            "Medidas internas: 400 x 300 x 250 mm (± 2 mm)."
        ),
    },
    # ─────────────────────────────────────────────
    # EIM05-8008 — Etiqueta Zebra
    # ─────────────────────────────────────────────
    {
        "tipo": "etiqueta_zebra",
        "codigo_base": "EIM05-8008",
        "variante": "",
        "revision": 0,
        "cliente": "Logística Norte S.R.L.",
        "producto": "Etiqueta térmica 100 x 150 mm",
        "titulo": "Etiqueta Zebra EIM05-8008",
        "observaciones": (
            "Tipo: etiqueta térmica directa, sin ribbon.\n"
            "Adhesivo: permanente, uso general, rango -20°C a +70°C.\n"
            "Soporte: papel couché blanco 80 g/m².\n"
            "Dimensiones: 100 x 150 mm.\n"
            "Contenido de la etiqueta:\n"
            "  - Código de barras Code128 (Nro. de pedido)\n"
            "  - Nro. de pedido, cliente y dirección de envío\n"
            "  - Peso total del bulto y cantidad de bultos\n"
            "  - Fecha de armado y operador\n"
            "Impresora: Zebra ZT411 - 300 dpi.\n"
            "Lenguaje: ZPL II.\n"
            "Densidad de impresión: 15 (oscuro)."
        ),
    },
    # ─────────────────────────────────────────────
    # BOCUS3 — Diseño Gráfico
    # ─────────────────────────────────────────────
    {
        "tipo": "diseno_grafico",
        "codigo_base": "BOCUS3",
        "variante": "",
        "revision": 0,
        "cliente": "Alimentos del Valle S.A.",
        "producto": "Bolsa stand-up pouch 500 g",
        "titulo": "Diseño gráfico bolsa BOCUS3",
        "observaciones": (
            "Diseño full color con acabado mate.\n"
            "Frente: imagen del producto, marca del cliente y peso neto.\n"
            "Dorso: tabla nutricional, ingredientes y código de barras.\n"
            "Colores Pantone:\n"
            "  - 186 C (rojo)\n"
            "  - 286 C (azul)\n"
            "  - 116 C (amarillo)\n"
            "Barniz UV sectorizado sobre el logo principal.\n"
            "Código de barras: EAN-13, alto 25 mm, ubicación inferior derecho.\n"
            "Etiqueta de lote: aplicada por impresora térmica en línea."
        ),
    },
    # ─────────────────────────────────────────────
    # BOCUS3 — Material de Empaque
    # ─────────────────────────────────────────────
    {
        "tipo": "material_empaque",
        "codigo_base": "BOCUS3",
        "variante": "",
        "revision": 0,
        "cliente": "Alimentos del Valle S.A.",
        "producto": "Bolsa stand-up pouch 500 g",
        "titulo": "Especificación material BOCUS3",
        "observaciones": (
            "Estructura: BOPP 20 µm / PEBD 60 µm.\n"
            "Espesor total: 80 µm (± 5%).\n"
            "Cierre: zipper hermético.\n"
            "Base: fuelle inferior para stand-up.\n"
            "Barrera al oxígeno: < 30 cm³/m²·24h.\n"
            "Barrera a la humedad: < 5 g/m²·24h.\n"
            "Apto para contacto directo con alimentos (FDA / ANMAT).\n"
            "Impresión: flexografía 8 colores, registro ± 0,5 mm.\n"
            "Ancho de bobina: 520 mm.\n"
            "Diámetro de bobina: 400 mm máx."
        ),
    },
]


def ya_existe(codigo_base: str, variante: str, tipo: str) -> bool:
    """True si ya hay una entrada con ese código + variante + tipo + rev 0."""
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("""
        SELECT id FROM especificaciones_generadas
        WHERE codigo_base = ? AND variante = ? AND tipo = ? AND revision = 0
    """, (codigo_base.upper(), variante.upper(), tipo))
    row = cur.fetchone()
    conn.close()
    return row is not None


def borrar_dummies():
    """Elimina los dummies existentes (mismo código + variante + tipo que vamos a crear)."""
    conn = get_db_connection()
    cur = conn.cursor()
    borrados = 0
    for d in DUMMIES:
        cur.execute("""
            DELETE FROM especificaciones_generadas
            WHERE codigo_base = ? AND variante = ? AND tipo = ?
        """, (d["codigo_base"].upper(), d["variante"].upper(), d["tipo"]))
        borrados += cur.rowcount
    conn.commit()
    conn.close()
    return borrados


def crear_dummy(d: dict) -> int | None:
    """Genera el PDF + guarda el registro. Devuelve el id o None si ya existía."""
    if ya_existe(d["codigo_base"], d["variante"], d["tipo"]):
        print(f"  ⏭  Ya existe: {d['codigo_base']}{d['variante']} ({d['tipo']})")
        return None

    datos = {
        "codigo_base":      d["codigo_base"],
        "variante":         d["variante"],
        "revision":         d["revision"],
        "revision_str":     f"{d['revision']:02d}",
        "codigo_completo":  storage.codigo_completo(d["codigo_base"], d["variante"]),
        "cliente":          d["cliente"],
        "producto":         d["producto"],
        "titulo":           d["titulo"],
        "observaciones":    d["observaciones"],
        "tipo_nombre":      TIPOS[d["tipo"]],
        "usuario":          "admin",
        "fecha_generacion": datetime.now().strftime("%d/%m/%Y %H:%M"),
        "logo_base64":      logo_base64(),
    }

    # Renderizar el template + generar el PDF dentro del app context
    with app.app_context():
        html = app.jinja_env.get_template(f"pdf/{d['tipo']}.html").render(datos=datos)
        pdf_bytes = generar_pdf(html)

    id_esp = storage.guardar_especificacion(
        id_usuario=1,
        usuario_nombre="admin",
        tipo=d["tipo"],
        codigo_base=d["codigo_base"],
        variante=d["variante"],
        revision=d["revision"],
        titulo=d["titulo"],
        cliente=d["cliente"],
        producto=d["producto"],
        datos=datos,
        pdf_bytes=pdf_bytes,
    )
    print(f"  ✅ {datos['codigo_completo']:<15} ({d['tipo']})  →  id={id_esp}")
    return id_esp


def main():
    reset = "--reset" in sys.argv

    print("=" * 65)
    print("  CARGA DE DATOS DUMMY")
    print("=" * 65)

    if reset:
        n = borrar_dummies()
        print(f"\n🗑  Borrados {n} registros previos\n")
    else:
        print("\n(Usá --reset para borrar los previos y recrearlos)\n")

    for d in DUMMIES:
        try:
            crear_dummy(d)
        except Exception as e:
            print(f"  ❌ Error con {d['codigo_base']}{d['variante']} ({d['tipo']}): {e}")

    print("\n" + "=" * 65)
    print("  LISTO")
    print("=" * 65)
    print("\nIngresá a http://192.168.16.109:5001/ para verlos en el panel")


if __name__ == "__main__":
    main()