# ver_planteo_y_anexo_dg.py
from pathlib import Path

RUTA = "plantillas/diseno_grafico.fodt"

with open(RUTA, encoding='utf-8') as f:
    contenido = f.read()

# 1. Bloque del planteo (desde ELEMENTOS DEL PLANTEO hasta 5.2)
print("=" * 70)
print("BLOQUE 1: TABLA DEL PLANTEO GRÁFICO")
print("=" * 70)
idx = contenido.find('ELEMENTOS DEL PLANTEO')
if idx != -1:
    # Desde acá hasta 5.2 o hasta ~5000 chars
    fin = contenido.find('MUESTRAS DE REFERENCIA', idx)
    if fin == -1:
        fin = contenido.find('5.2', idx)
    if fin == -1:
        fin = idx + 5000
    print(contenido[idx:fin])

# 2. Bloque del anexo
print("\n" + "=" * 70)
print("BLOQUE 2: ANEXO")
print("=" * 70)
idx = contenido.find('ANEXO')
if idx != -1:
    # Múltiples apariciones: buscar la última (la del body)
    indices = []
    start = 0
    while True:
        i = contenido.find('ANEXO', start)
        if i == -1:
            break
        indices.append(i)
        start = i + 1
    print(f"Encontrado ANEXO {len(indices)} veces")

    # Mostrar la última (body)
    if indices:
        idx = indices[-1]
        print(contenido[idx-500:idx+3500])
else:
    print("No se encontró 'ANEXO'")

# 3. Buscar versiones_anteriores / for en el .fodt
print("\n" + "=" * 70)
print("BLOQUE 3: {% for %} y versiones_anteriores")
print("=" * 70)
print(f"versiones_anteriores: {contenido.count('versiones_anteriores')}")
print(f"{% for %}: {contenido.count('{% for')}")
print(f"{{ v. }}: {contenido.count('{{ v.')}")

# Mostrar cada {% for %} con contexto
import re
for m in re.finditer(r'\{%\s*for\s+\w+\s+in\s+(\w+)\s*%\}', contenido):
    ini = max(0, m.start() - 100)
    fin = min(len(contenido), m.end() + 300)
    print(f"\n--- for en pos {m.start()} ---")
    print(contenido[ini:fin])