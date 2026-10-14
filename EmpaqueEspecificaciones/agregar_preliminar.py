# agregar_preliminar.py
"""
Agrega el condicional {% if es_preliminar == "1" %} al header del .fodt
para mostrar -PRELIMINAR- debajo del código del documento.

Uso:
    python agregar_preliminar.py plantillas\diseno_grafico.fodt
"""
import re
import shutil
import sys
from pathlib import Path


def main():
    if len(sys.argv) != 2:
        print("Uso: python agregar_preliminar.py <plantillas/archivo.fodt>")
        sys.exit(1)

    ruta = Path(sys.argv[1])
    if not ruta.exists():
        print(f"❌ No existe: {ruta}")
        sys.exit(1)

    contenido = ruta.read_text(encoding='utf-8')

    if 'es_preliminar' in contenido:
        print("ℹ️  El archivo ya tenía el condicional 'es_preliminar'")
        print("   Si querés volver a aplicarlo, restaurá el backup y corré de nuevo.")
        sys.exit(0)

    backup = ruta.with_suffix('.fodt.bak7')
    shutil.copy2(ruta, backup)
    print(f"💾 Backup: {backup}")
    print(f"📄 Original: {len(contenido):,} caracteres")

    # ─── Buscar el patrón del header ───
    patrones = [
        # Variante 1: con <text:span text:style-name="T3"/> al lado
        re.compile(
            r'(<text:span text:style-name="T3">\s*\{\{\s*codigo_base\s*\}\}\s*\{\{\s*variante\s*\}\}\s*</text:span>)'
            r'(\s*<text:span text:style-name="T3"/>)',
            re.DOTALL
        ),
        # Variante 2: solo el span
        re.compile(
            r'(<text:span text:style-name="T3">\s*\{\{\s*codigo_base\s*\}\}\s*\{\{\s*variante\s*\}\}\s*</text:span>)',
            re.DOTALL
        ),
    ]

    insercion = (
        '{% if es_preliminar == "1" %}'
        '<text:line-break/>'
        '<text:span text:style-name="T3">-PRELIMINAR-</text:span>'
        '{% endif %}'
    )

    for i, patron in enumerate(patrones):
        coincidencias = patron.findall(contenido)
        if coincidencias:
            if i == 0:
                nuevo = patron.sub(
                    lambda m: m.group(1) + insercion + m.group(2),
                    contenido,
                )
            else:
                nuevo = patron.sub(
                    lambda m: m.group(1) + insercion,
                    contenido,
                )

            ruta.write_text(nuevo, encoding='utf-8')
            print(f"✅ Modificado usando patrón {i+1}")
            print(f"   Coincidencias: {len(coincidencias)}")
            print(f"💾 Nuevo tamaño: {len(nuevo):,} caracteres")
            print(f"✅ Guardado en: {ruta}")
            return

    # ─── No se encontró el patrón ───
    print("❌ No se encontró el patrón del header")
    print("   Buscando dónde debería estar...\n")

    for m in re.finditer(r'\{\{\s*codigo_base\s*\}\}', contenido):
        inicio = max(0, m.start() - 200)
        fin    = min(len(contenido), m.end() + 200)
        print(f"   ...{contenido[inicio:fin]}...\n")

    print("⚠️  Copiá ese fragmento y pasámelo para ajustar el script.")


if __name__ == "__main__":
    main()