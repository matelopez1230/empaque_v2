#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
patch_etiqueta_zebra.py
Parchea el FODT de etiqueta zebra (ET) segun los cambios acordados.

Uso:
    python patch_etiqueta_zebra.py etiqueta_zebra.fodt
    python patch_etiqueta_zebra.py etiqueta_zebra.fodt -o patched.fodt
    python patch_etiqueta_zebra.py etiqueta_zebra.fodt --dry-run
    python patch_etiqueta_zebra.py etiqueta_zebra.fodt --debug
"""

import argparse
import re
import sys
import traceback
from pathlib import Path

# -- Consola segura (Windows cp1252 -> UTF-8 con reemplazo) -------------------
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass


def p(msg=""):
    """print con flush garantizado."""
    print(msg, flush=True)


# -- Utilidades --------------------------------------------------------------
LOG = []


def _sub1(text, old, new, expected=None, label=""):
    n = text.count(old)
    if n == 0:
        LOG.append(f"  [FAIL] {label}: NO encontrado")
        return text
    if expected is not None and n != expected:
        LOG.append(f"  [FAIL] {label}: esperaba {expected}, encontre {n}")
    else:
        LOG.append(f"  [OK]   {label}: {n} reemplazo(s)")
    return text.replace(old, new)


# -- Bloques de parcheo ------------------------------------------------------
def bloque1_header(text):
    LOG.append("[Bloque 1] Header y codigos")

    text = _sub1(text, "{{Nombre}}", "{{ codigo_base }}", label="1.1 Nombre->codigo_base")
    text = _sub1(text, "{{variante}}", "{{ variante }}", label="1.2 variante spacing")

    old_title = (
        '<text:p text:style-name="P4" loext:marker-style-name="T2">'
        '<text:span text:style-name="T2">{{ codigo_base }}{{ variante }}</text:span>'
        '</text:p>'
    )
    new_title = (
        '<text:p text:style-name="P4" loext:marker-style-name="T2">'
        '<text:span text:style-name="T2">{{ codigo_base }}{{ variante }}</text:span>'
        '{% if es_preliminar == "1" %}<text:line-break/>'
        '<text:span text:style-name="T2">-PRELIMINAR-</text:span>'
        '{% endif %}'
        '</text:p>'
    )
    text = _sub1(text, old_title, new_title, expected=1, label="1.3 preliminar en titulo")

    text = _sub1(text, "{{USUARIO}}", "{{ usuario }}",   expected=1, label="1.5 footer usuario")
    text = _sub1(text, "{{APRUEBA}}", "{{ aprobador }}", expected=1, label="1.5 footer aprobador")
    return text


def bloque2_fechas(text):
    LOG.append("[Bloque 2] Fechas, revision, paginacion")

    text = _sub1(text, "{{DD-MM-AAAA}}", "{{ fecha_revision }}",
                 expected=1, label="2.1 fecha header")
    text = _sub1(text, "{{NUM_REV}}", "{{ revision_str }}",
                 expected=1, label="2.2 revision header")

    old_page = (
        '<text:p text:style-name="P6" loext:marker-style-name="T3">'
        '<text:span text:style-name="T3">{{n}} de {{m}}</text:span>'
        '</text:p>'
    )
    new_page = (
        '<text:p text:style-name="P6" loext:marker-style-name="T3">'
        '<text:page-number text:style-name="T3" text:select-page="current">1</text:page-number>'
        '<text:span text:style-name="T3"> de </text:span>'
        '<text:page-count text:style-name="T3">1</text:page-count>'
        '</text:p>'
    )
    text = _sub1(text, old_page, new_page, expected=1, label="2.3 paginacion nativa")
    return text


def bloque3_imagen(text):
    LOG.append("[Bloque 3] Imagen")
    return _sub1(text, "{{IMAGEN}}", "{{ imagen }}", expected=1, label="3.1 imagen")


def bloque4_anexo(text):
    LOG.append("[Bloque 4] Anexo dinamico")

    text = _sub1(text, "{{DD\u2014MM-AAAA}}", "{{ v.fecha_revision }}",
                 expected=1, label="4.2 anexo fecha")
    text = _sub1(text, "{{NUM-REV}}", "{{ v.revision }}",
                 expected=1, label="4.2 anexo rev")
    text = _sub1(text, "{{TEXTO_REVISION}}", "{{ v.anexo }}",
                 expected=1, label="4.2 anexo texto")

    # 4.1 for versiones_anteriores
    row_start_re = re.compile(
        r'<table:table-row table:style-name="Tabla5\.1">\s*'
        r'<table:table-cell table:style-name="Tabla5\.A2"',
        re.DOTALL,
    )
    m = row_start_re.search(text)
    if not m:
        LOG.append("  [FAIL] 4.1 for: no se encontro la fila de datos (A2)")
    else:
        start_idx = m.start()
        try:
            end_idx = text.index("</table:table-row>", start_idx) + len("</table:table-row>")
            row = text[start_idx:end_idx]
            text = (
                text[:start_idx]
                + "{% for v in versiones_anteriores %}\n"
                + row
                + "\n{% endfor %}"
                + text[end_idx:]
            )
            LOG.append("  [OK]   4.1 for versiones_anteriores")
        except ValueError:
            LOG.append("  [FAIL] 4.1 for: no se encontro cierre </table:table-row>")

    # 4.3 quitar fila vacia
    empty_re = re.compile(
        r'\s*<table:table-row table:style-name="Tabla5\.1">\s*'
        r'<table:table-cell table:style-name="Tabla5\.A3"[^>]*>\s*'
        r'<text:p text:style-name="P51"[^>]*/>\s*'
        r'</table:table-cell>\s*'
        r'<table:table-cell table:style-name="Tabla5\.B3"[^>]*>\s*'
        r'<text:p text:style-name="P51"[^>]*/>\s*'
        r'</table:table-cell>\s*'
        r'<table:table-cell table:style-name="Tabla5\.C3"[^>]*>\s*'
        r'<text:p text:style-name="P52"[^>]*/>\s*'
        r'</table:table-cell>\s*'
        r'</table:table-row>',
        re.DOTALL,
    )
    text, n = empty_re.subn("", text, count=1)
    LOG.append(f"  [{'OK  ' if n else 'FAIL'}] 4.3 fila vacia {'eliminada' if n else 'NO encontrada'}")

    # 4.4 if incluir_anexo (envolver Marco3)
    start_marker = (
        '<text:p text:style-name="P48" loext:marker-style-name="T25">'
        '<draw:frame draw:style-name="fr3" draw:name="Marco3"'
    )
    end_marker = '<text:p text:style-name="P53" loext:marker-style-name="T37">'

    start_idx = text.find(start_marker)
    if start_idx == -1:
        LOG.append("  [FAIL] 4.4 if: no se encontro Marco3")
    else:
        end_idx = text.find(end_marker, start_idx)
        if end_idx == -1:
            LOG.append("  [FAIL] 4.4 if: no se encontro el siguiente P53")
        else:
            block = text[start_idx:end_idx].rstrip()
            text = (
                text[:start_idx]
                + "{% if incluir_anexo %}\n"
                + block
                + "\n{% endif %}\n"
                + text[end_idx:]
            )
            LOG.append("  [OK]   4.4 if incluir_anexo")

    return text


# -- Orquestador -------------------------------------------------------------
def aplicar_todos(text):
    text = bloque1_header(text)
    text = bloque2_fechas(text)
    text = bloque3_imagen(text)
    text = bloque4_anexo(text)
    LOG.append("[Bloques 5-6] Sin cambios (secciones fijas, numeracion intacta)")
    return text


PROHIBIDOS = [
    "{{Nombre}}", "{{IMAGEN}}", "{{DD-MM-AAAA}}", "{{NUM_REV}}",
    "{{n}}", "{{m}}",
    "{{DD\u2014MM-AAAA}}", "{{NUM-REV}}", "{{TEXTO_REVISION}}",
    "{{variante}}", "{{USUARIO}}", "{{APRUEBA}}",
]
REQUERIDOS = [
    "{{ codigo_base }}", "{{ variante }}", "{{ fecha_revision }}",
    "{{ revision_str }}", "{{ imagen }}", "{{ usuario }}", "{{ aprobador }}",
    "{{ v.fecha_revision }}", "{{ v.revision }}", "{{ v.anexo }}",
    "{% for v in versiones_anteriores %}", "{% endfor %}",
    "{% if incluir_anexo %}", "{% endif %}",
]


def main():
    p(">>> patch_etiqueta_zebra.py iniciado")
    ap = argparse.ArgumentParser(description="Parchea el FODT de etiqueta zebra (ET)")
    ap.add_argument("fodt", help="Ruta al .fodt original")
    ap.add_argument("-o", "--out", help="Ruta de salida (default: <input>_patched.fodt)")
    ap.add_argument("--dry-run", action="store_true", help="Analizar sin escribir")
    ap.add_argument("--debug", action="store_true", help="Mostrar traceback completo")
    args = ap.parse_args()

    src = Path(args.fodt)
    p(f">>> Input: {src.resolve()}")
    if not src.exists():
        p(f"[ERROR] No existe: {src}")
        sys.exit(1)

    try:
        original = src.read_text(encoding="utf-8")
    except UnicodeDecodeError as e:
        p(f"[ERROR] El FODT no es UTF-8: {e}")
        sys.exit(1)

    p(f">>> Leido ({len(original):,} chars)")
    p("")

    patched = aplicar_todos(original)

    for linea in LOG:
        p(linea)
    p("")
    p(f">>> Resultado: {len(original):,} -> {len(patched):,} chars")
    p("")

    residuales = [x for x in PROHIBIDOS if x in patched]
    faltantes  = [x for x in REQUERIDOS if x not in patched]

    if residuales:
        p(f"[WARN] Placeholders prohibidos que quedaron: {residuales}")
    else:
        p("[OK]   No quedan placeholders prohibidos")

    if faltantes:
        p(f"[WARN] Placeholders requeridos que faltan: {faltantes}")
    else:
        p("[OK]   Todos los placeholders requeridos estan presentes")
    p("")

    if args.dry_run:
        p(">>> [dry-run] No se escribio archivo.")
        return

    if residuales or faltantes:
        p(">>> Abortando escritura por diagnosticos negativos.")
        sys.exit(2)

    out = Path(args.out) if args.out else src.with_name(src.stem + "_patched.fodt")
    out.write_text(patched, encoding="utf-8")
    p(f">>> Escrito: {out.resolve()}")
    p(">>> patch_etiqueta_zebra.py finalizado OK")


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except Exception:
        p("[ERROR] Excepcion no controlada:")
        p(traceback.format_exc())
        sys.exit(1)