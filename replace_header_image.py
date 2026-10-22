#!/usr/bin/env python3
"""
Script para detectar imágenes en cabeceras de archivos .fodt
y evaluar si su reemplazo es seguro.
"""
import sys
from lxml import etree

# Namespaces comunes en OpenDocument
NS = {
    'office': 'urn:oasis:names:tc:opendocument:xmlns:office:1.0',
    'style': 'urn:oasis:names:tc:opendocument:xmlns:style:1.0',
    'draw': 'urn:oasis:names:tc:opendocument:xmlns:drawing:1.0',
    'text': 'urn:oasis:names:tc:opendocument:xmlns:text:1.0',
    'xlink': 'http://www.w3.org/1999/xlink'
}

def analizar_cabeceras(ruta_fodt):
    try:
        # Parseamos el archivo XML
        tree = etree.parse(ruta_fodt)
        root = tree.getroot()
    except Exception as e:
        print(f"❌ Error al parsear el archivo: {e}")
        return

    print(f"📄 Analizando: {ruta_fodt}\n")

    # 1. Buscamos todas las imágenes dentro de marcos (draw:frame)
    # que estén dentro de un estilo de cabecera.
    # XPath: Busca cualquier draw:image cuyo ancestro sea un style:header
    imagenes_en_marcos = root.xpath('//style:header//draw:frame/draw:image', namespaces=NS)
    
    # 2. Buscamos imágenes de fondo en las propiedades de cabecera
    imagenes_de_fondo = root.xpath('//style:header//style:header-footer-properties/style:background-image', namespaces=NS)

    total_imagenes = len(imagenes_en_marcos) + len(imagenes_de_fondo)
    
    if total_imagenes == 0:
        print("✅ No se encontraron imágenes en las cabeceras de este documento.")
        return

    print(f"🖼️  Se encontraron {total_imagenes} imagen(es) en las cabeceras.\n")

    # --- Analizar Imágenes en Marcos (draw:frame > draw:image) ---
    for i, img_elem in enumerate(imagenes_en_marcos, 1):
        print(f"--- Imagen en Marco #{i} ---")
        href = img_elem.get('{http://www.w3.org/1999/xlink}href')
        
        # Buscamos si tiene datos binarios incrustados (office:binary-data)
        bin_data = img_elem.find('office:binary-data', namespaces=NS)
        
        if href:
            print(f"   Tipo: Enlace externo")
            print(f"   Ruta: {href}")
            print(f"   ⚠️  ADVERTENCIA: Es un enlace. Si el archivo se mueve a otro equipo, la imagen se romperá.")
            print(f"   💡 Consejo: Para mayor seguridad, considera incrustar la imagen (embed).")
        elif bin_data is not None:
            print(f"   Tipo: Imagen incrustada (Base64)")
            # Verificamos el tamaño de los datos para dar una idea de la resolución
            data_len = len(bin_data.text) if bin_data.text else 0
            print(f"   📦 Tamaño de los datos Base64: ~{data_len:,} caracteres")
            print(f"   ✅ SEGURO: Los datos están dentro del archivo. El reemplazo es viable.")
        else:
            print(f"   ⚠️  ADVERTENCIA: No se encontró ni enlace (href) ni datos binarios (binary-data).")
            print(f"   ❓ Estado desconocido. Podría ser una referencia a un estilo de imagen no resuelta.")
        print()

    # --- Analizar Imágenes de Fondo (style:background-image) ---
    for i, bg_img_elem in enumerate(imagenes_de_fondo, 1):
        print(f"--- Imagen de Fondo #{i} ---")
        bin_data = bg_img_elem.find('office:binary-data', namespaces=NS)
        if bin_data is not None:
            print(f"   Tipo: Imagen de fondo incrustada (Base64)")
            print(f"   ✅ SEGURO: Los datos están dentro del archivo.")
            print(f"   💡 Nota: Este es el caso típico de `style:background-image` dentro de `style:header-footer-properties`.")
        else:
            print(f"   ⚠️  ADVERTENCIA: La imagen de fondo no tiene datos binarios incrustados.")
            print(f"   ❓ Podría ser un enlace externo o una referencia no resuelta.")
        print()

if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Uso: python script.py <archivo.fodt>")
        sys.exit(1)
    analizar_cabeceras(sys.argv[1])