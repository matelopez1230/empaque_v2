#!/usr/bin/env python3
"""
Reemplaza imágenes PNG en las cabeceras (style:header) de archivos .fodt.

Uso:
  python reemplazar_png_header.py documento.fodt nuevo_logo.png --backup --adjust-frame
  python reemplazar_png_header.py documento.fodt nuevo_logo.png --first
"""
import argparse
import base64
import shutil
import sys
import textwrap
from pathlib import Path
from lxml import etree

NS = {
    'office': 'urn:oasis:names:tc:opendocument:xmlns:office:1.0',
    'style':  'urn:oasis:names:tc:opendocument:xmlns:style:1.0',
    'draw':   'urn:oasis:names:tc:opendocument:xmlns:drawing:1.0',
    'svg':    'urn:oasis:names:tc:opendocument:xmlns:svg-compatible:1.0',
    'xlink':  'http://www.w3.org/1999/xlink',
    'loext':  'urn:org:documentfoundation:names:experimental:office:xmlns:loext:1.0',
}

def png_dimensions(data: bytes):
    """Extrae ancho y alto del chunk IHDR (bytes 16-24)."""
    if data[:8] != b'\x89PNG\r\n\x1a\n':
        raise ValueError("El archivo no es un PNG válido")
    return int.from_bytes(data[16:20], 'big'), int.from_bytes(data[20:24], 'big')

def read_length_cm(s: str):
    """Convierte '2.54cm', '1in', '100pt', etc. a (valor_en_cm, unidad)."""
    if not s:
        return None, None
    for u, f in [('cm', 1), ('mm', 0.1), ('in', 2.54),
                 ('pt', 2.54/72), ('pc', 2.54/6), ('px', 2.54/96)]:
        if s.endswith(u):
            return float(s[:-len(u)]) * f, u
    try:
        return float(s), 'cm'
    except ValueError:
        return None, None

def cm_to_length(value_cm: float, unit: str) -> str:
    f = {'cm': 1, 'mm': 0.1, 'in': 2.54,
         'pt': 2.54/72, 'pc': 2.54/6, 'px': 2.54/96}.get(unit, 1)
    return f"{value_cm / f:.4f}".rstrip('0').rstrip('.') + unit

def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('fodt', help='Archivo .fodt a modificar')
    ap.add_argument('png',  help='Nuevo PNG de alta calidad')
    ap.add_argument('--backup', action='store_true', help='Crear .bak antes de modificar')
    ap.add_argument('--adjust-frame', action='store_true',
                    help='Ajustar alto del marco para preservar relación de aspecto')
    ap.add_argument('--first', action='store_true',
                    help='Reemplazar solo la primera imagen (por defecto todas las del header)')
    args = ap.parse_args()

    png_path = Path(args.png)
    if not png_path.exists():
        print(f"❌ No existe: {png_path}"); return 1

    png_bytes = png_path.read_bytes()
    new_w, new_h = png_dimensions(png_bytes)
    new_ratio = new_w / new_h
    b64_new = '\n'.join(textwrap.wrap(
        base64.b64encode(png_bytes).decode('ascii'), 76))
    print(f"🖼️  Nuevo PNG: {png_path.name} — {new_w}×{new_h}px, "
          f"{len(png_bytes):,} bytes  (ratio {new_ratio:.3f})")

    fodt_path = Path(args.fodt)
    if args.backup:
        bak = fodt_path.with_suffix(fodt_path.suffix + '.bak')
        shutil.copy2(fodt_path, bak)
        print(f"💾 Backup: {bak}")

    parser = etree.XMLParser(huge_tree=True, remove_blank_text=False)
    tree = etree.parse(str(fodt_path), parser)
    root = tree.getroot()

    images = root.xpath('//style:header//draw:frame/draw:image', namespaces=NS)
    if not images:
        print("⚠️  No se encontraron imágenes dentro de <style:header>.")
        return 1

    targets = images[:1] if args.first else images
    print(f"🔍 {len(images)} imagen(es) en cabeceras; reemplazando {len(targets)}.\n")

    for i, img in enumerate(targets, 1):
        # 1) Sustituir/insertar <office:binary-data>
        bin_el = img.find('office:binary-data', namespaces=NS)
        if bin_el is None:
            bin_el = etree.SubElement(img, f"{{{NS['office']}}}binary-data")
        bin_el.text = b64_new

        # 2) Actualizar loext:mime-type si existía (ej: JPEG → PNG)
        mt = f"{{{NS['loext']}}}mime-type"
        if mt in img.attrib:
            img.set(mt, 'image/png')

        # 3) Ajustar dimensiones del marco si se pidió
        frame = img.getparent()
        if args.adjust_frame and frame is not None \
                and frame.tag == f"{{{NS['draw']}}}frame":
            w_attr = f"{{{NS['svg']}}}width"
            h_attr = f"{{{NS['svg']}}}height"
            w_val, h_val = frame.get(w_attr), frame.get(h_attr)
            w_cm, w_u = read_length_cm(w_val)
            h_cm, h_u = read_length_cm(h_val)

            if w_cm and h_cm:
                old_ratio = w_cm / h_cm
                new_h_cm = w_cm / new_ratio
                frame.set(h_attr, cm_to_length(new_h_cm, h_u or 'cm'))
                print(f"   #{i}: marco {w_val}×{h_val} (ratio {old_ratio:.3f}) "
                      f"→ alto {frame.get(h_attr)} (ratio {new_ratio:.3f})")
            else:
                print(f"   #{i}: ⚠️ no pude parsear dimensiones del marco "
                      f"({w_val!r}×{h_val!r}); se mantiene tal cual.")
        else:
            print(f"   #{i}: imagen reemplazada (marco sin tocar).")

    # 4) Guardar
    tree.write(str(fodt_path), xml_declaration=True,
               encoding='UTF-8', pretty_print=False)
    print(f"\n🎉 Listo: {len(targets)} imagen(es) reemplazada(s) en {fodt_path}")
    print("💡 Validación opcional: https://odfvalidator.org/")
    return 0

if __name__ == '__main__':
    sys.exit(main())