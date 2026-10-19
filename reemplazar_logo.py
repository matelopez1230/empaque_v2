# reemplazar_logo.py
"""
Reemplaza la imagen del header en los .fodt indicados.

Uso:
    python reemplazar_logo.py --nueva uploads/mi_logo.png
    python reemplazar_logo.py --nueva uploads/mi_logo.png --solo etiqueta
    python reemplazar_logo.py --revert
"""
from __future__ import annotations
import argparse, base64, re, shutil, sys
from io import BytesIO
from pathlib import Path

BASE = Path(__file__).resolve().parent
PLANTILLAS = BASE / "plantillas"
BAK_DIR = BASE / "plantillas" / "_logos_backup"
BAK_DIR.mkdir(parents=True, exist_ok=True)

ARCHIVOS = {
    "etiqueta":         "etiqueta.fodt",
    "diseno_grafico":   "diseno_grafico.fodt",
    "material_empaque": "material_empaque.fodt",
}

try:
    from PIL import Image
    TIENE_PIL = True
except ImportError:
    TIENE_PIL = False
    print("⚠️  Pillow no instalado. Voy a embeber la imagen tal cual, sin redimensionar.\n")


def _mime_de(ext: str) -> str:
    return {
        ".png":  "image/png",
        ".jpg":  "image/jpeg",
        ".jpeg": "image/jpeg",
        ".gif":  "image/gif",
        ".webp": "image/webp",
        ".bmp":  "image/bmp",
    }.get(ext.lower(), "image/png")


def _leer_original(fodt_path: Path):
    """Devuelve (mime, px_ancho, px_alto) del logo actual, o None si no hay."""
    c = fodt_path.read_text(encoding="utf-8")
    m = re.search(
        r'<draw:frame[^>]*draw:name="Imagen[^"]*"[^>]*>.*?'
        r'<draw:image[^>]*draw:mime-type="([^"]+)"[^>]*>\s*'
        r'<office:binary-data>([^<]+)</office:binary-data>',
        c, re.DOTALL,
    )
    if not m:
        return None

    datos = base64.b64decode(m.group(2).strip())
    if not TIENE_PIL:
        return (m.group(1), None, None)
    try:
        img = Image.open(BytesIO(datos))
        return (m.group(1), *img.size)
    except Exception:
        return (m.group(1), None, None)


def _preparar_imagen(ruta_nueva: Path, ancho_destino, alto_destino):
    """
    Devuelve (bytes, mime) listos para embeber.
    Si PIL está y tenemos dimensiones destino, redimensiona manteniendo aspecto.
    """
    datos = ruta_nueva.read_bytes()
    mime = _mime_de(ruta_nueva.suffix)

    if not TIENE_PIL or not ancho_destino or not alto_destino:
        return datos, mime

    try:
        img = Image.open(BytesIO(datos))
        if img.size != (ancho_destino, alto_destino):
            img = img.resize((ancho_destino, alto_destino), Image.LANCZOS)
        # Guardar como PNG siempre (más seguro para headers, sin pérdida)
        buf = BytesIO()
        img.save(buf, format="PNG", optimize=True)
        return buf.getvalue(), "image/png"
    except Exception as e:
        print(f"⚠️  No pude redimensionar ({e}), embebo tal cual.")
        return datos, mime


def _reemplazar_en(fodt_path: Path, nueva_bytes: bytes, nuevo_mime: str) -> int:
    c = fodt_path.read_text(encoding="utf-8")

    # Backup la primera vez
    bak = BAK_DIR / fodt_path.name
    if not bak.exists():
        shutil.copy2(fodt_path, bak)

    nuevo_b64 = base64.b64encode(nueva_bytes).decode("ascii")

    # Buscar el bloque <draw:image> del header y reemplazar su binary-data + mime
    patron = re.compile(
        r'(<draw:frame[^>]*draw:name="Imagen[^"]*"[^>]*>.*?'
        r'<draw:image[^>]*draw:mime-type=")([^"]+)("[^>]*>\s*'
        r'<office:binary-data>)([^<]+)(</office:binary-data>)',
        re.DOTALL,
    )

    def _sub(m):
        return (
            m.group(1) + nuevo_mime + m.group(3) +
            nuevo_b64 + m.group(5)
        )

    c_nuevo, n = patron.subn(_sub, c, count=1)
    if n == 0:
        return 0

    fodt_path.write_text(c_nuevo, encoding="utf-8")
    return n


def aplicar(ruta_nueva: Path, solo: str | None = None) -> int:
    if not ruta_nueva.exists():
        print(f"❌ No existe la imagen nueva: {ruta_nueva}")
        return 1

    print(f"🖼️  Imagen nueva: {ruta_nueva}  ({ruta_nueva.stat().st_size} bytes)\n")

    objetivos = ARCHIVOS
    if solo and solo in ARCHIVOS:
        objetivos = {solo: ARCHIVOS[solo]}
    elif solo:
        print(f"❌ Nombre inválido: {solo}. Opciones: {list(ARCHIVOS.keys())}")
        return 1

    for nombre, archivo in objetivos.items():
        p = PLANTILLAS / archivo
        if not p.exists():
            print(f"⏭️  {archivo}: no existe, salteo.")
            continue

        orig = _leer_original(p)
        if not orig:
            print(f"❌ {archivo}: no encontré el logo actual para copiar dimensiones.")
            continue

        _, px_w, px_h = orig
        print(f"📄 {archivo}:  original {px_w}×{px_h}px (o sin PIL)")

        nueva_bytes, nuevo_mime = _preparar_imagen(ruta_nueva, px_w, px_h)
        print(f"   → embebo {len(nueva_bytes)} bytes como {nuevo_mime}")

        n = _reemplazar_en(p, nueva_bytes, nuevo_mime)
        if n:
            print(f"   ✅ reemplazado ({n} bloque)")
        else:
            print(f"   ❌ no se pudo reemplazar")

    print()
    print(f"💾 Backups en: {BAK_DIR}")
    print(f"↩️  Para revertir: python reemplazar_logo.py --revert")
    return 0


def revertir() -> int:
    ok = 0
    for archivo in ARCHIVOS.values():
        p = PLANTILLAS / archivo
        bak = BAK_DIR / archivo
        if not p.exists() or not bak.exists():
            continue
        shutil.copy2(bak, p)
        print(f"✅ Restaurado: {archivo}")
        ok += 1
    if not ok:
        print("❌ No hay backups para restaurar.")
        return 1
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--nueva", type=Path, help="Ruta a la imagen nueva")
    ap.add_argument("--solo", help="Solo uno: etiqueta | diseno_grafico | material_empaque")
    ap.add_argument("--revert", action="store_true", help="Restaurar backups")
    args = ap.parse_args()

    if args.revert:
        return revertir()
    if not args.nueva:
        print("❌ Falta --nueva RUTA")
        return 1
    return aplicar(args.nueva, solo=args.solo)


if __name__ == "__main__":
    sys.exit(main())