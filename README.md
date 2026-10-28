# 📦 Empaque v2 - Generador de Especificaciones de Empaque

[![Python](https://img.shields.io/badge/Python-3.10%2B-blue.svg)](https://www.python.org/)
[![Flask](https://img.shields.io/badge/Flask-3.1.3-green.svg)](https://flask.palletsprojects.com/)
[![SQLite](https://img.shields.io/badge/SQLite-3-lightgrey.svg)](https://www.sqlite.org/)
[![License](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

Sistema web desarrollado para la **creación, gestión y envío automatizado de especificaciones de empaque**. Permite a los usuarios autenticados generar documentos PDF técnicos (etiquetas, material de empaque, diseño gráfico, etc.) a partir de formularios dinámicos, almacenarlos en base de datos y enviarlos por correo electrónico mediante una cola persistente con rate limiting.

---

## 🚀 Características Principales

- **Autenticación de usuarios** con roles (admin / usuario estándar) y cambio de contraseña.
- **Generación de PDFs** de alta calidad usando `WeasyPrint` y plantillas `.fodt` procesadas con LibreOffice.
- **Formularios especializados** para cada tipo de especificación:
  - Diseño Gráfico
  - Material de Empaque
  - Etiqueta
  - Etiqueta Zebra (con imagen obligatoria)
- **Sistema de revisiones** automático por código base + variante.
- **Cola de envíos de correo** con rate limiting (token bucket) y worker en segundo plano.
- **Integración con Microsoft Outlook** (vía `win32com`) para el envío de correos con adjuntos PDF.
- **Gestión de permisos** granulares por usuario y por borrador (tablas `permisos_globales`, `permisos_especificos`).
- **Notificaciones internas** para los usuarios.
- **Almacenamiento seguro** de imágenes y archivos generados.
- **Migraciones automáticas** para la base de datos (scripts idempotentes).

---

## 🛠️ Tecnologías Utilizadas

| Componente | Tecnología |
|------------|------------|
| Backend | Flask 3.1.3 |
| Base de Datos | SQLite 3 |
| Generación PDF | WeasyPrint 63.1, LibreOffice (opcional para `.fodt`) |
| Servidor WSGI | Waitress 3.0.2 |
| Autenticación | Werkzeug Security (hash de contraseñas) |
| Envío de Correo | Microsoft Outlook (win32com) |
| Procesamiento de Imágenes | Pillow 12.3.0 |
| Plantillas | Jinja2 |

---

## 📁 Estructura del Proyecto

```
empaque_v2/
├── app.py                     # Punto de entrada de la aplicación Flask
├── auth.py                    # Blueprint de autenticación (login, logout, cambio de contraseña)
├── db.py                      # Conexión a la base de datos SQLite
├── routes_pdf.py              # Blueprint principal: formularios, generación y gestión de PDFs
├── pdf_utils.py               # Utilidades para generar PDFs (WeasyPrint + LibreOffice)
├── storage.py                 # Lógica de persistencia (publicados, borradores, envíos)
├── envios_queue.py            # Cola de envíos con rate limiting y worker en background
├── mailer.py                  # Integración con Outlook para envío de correos
├── permisos.py                # Decoradores de autorización (login_required, admin_required)
├── __init_db__.py             # Script de inicialización de la base de datos y usuario admin
├── migracion_permisos.py      # Migración para tablas de permisos y notificaciones
├── migrar_correos.py          # Migración para tablas de correo y columna email en usuarios
├── dump_schema.py             # Utilidad para volcar el esquema de la base de datos
├── requirements.txt           # Dependencias del proyecto
├── instance/                  # Base de datos SQLite (especificaciones.db)
├── uploads/                   # Archivos subidos (imágenes, PDFs temporales)
├── plantillas/                # Plantillas .fodt para generación de PDFs
├── static/                    # Archivos estáticos (CSS, JS, imágenes)
└── templates/                 # Plantillas HTML (Jinja2)
    ├── pdf/
    ├── base.html
    ├── buscar.html
    ├── formulario.html
    ├── formulario_etiqueta.html
    ├── formulario_etiqueta_zebra.html
    ├── formulario_material_empaque.html
    ├── login.html
    └── panel.html
```
*Plantillas está vacio para que el usuario pueda ingresar sus propias plantillas
---

## ⚙️ Instalación y Configuración

### 1. Clonar el repositorio
```bash
git clone https://github.com/matelopez1230/empaque_v2.git
cd empaque_v2
```

### 2. Crear y activar un entorno virtual
```bash
python -m venv venv
# Windows
venv\Scripts\activate
# Linux/macOS
source venv/bin/activate
```

### 3. Instalar dependencias
```bash
pip install -r requirements.txt
```

> **Nota:** Para la generación de PDFs con LibreOffice, asegúrate de tener instalado [LibreOffice](https://www.libreoffice.org/) en el sistema. El código busca `soffice.exe` en las rutas típicas de Windows. Si usas otro SO, ajusta las rutas en `pdf_utils.py`.

### 4. Inicializar la base de datos
```bash
python __init_db__.py
```
Esto creará la base de datos `instance/especificaciones.db` y el usuario administrador por defecto:
- **Usuario:** `admin`
- **Contraseña:** `admin123`

> **Importante:** Cambia la contraseña del admin después del primer inicio de sesión.

### 5. Ejecutar migraciones (opcional pero recomendado)
```bash
python migracion_permisos.py
python migrar_correos.py
```
Estas migraciones agregan las tablas de permisos, notificaciones, contactos de correo y la columna `email` en usuarios.

### 6. Configurar variables de entorno (opcional)
Puedes crear un archivo `.env` en la raíz del proyecto con las siguientes variables:

```env
# Rate limiting para envíos de correo
ENVIOS_BURST=10
ENVIOS_INTERVALO_SEG=2.0

# Modo de prueba para correos (no envía realmente)
DRY_RUN=0
```

### 7. Iniciar la aplicación
```bash
python app.py
```
La aplicación estará disponible en `http://localhost:5001`.

---

## 🖥️ Uso Básico

1. **Iniciar sesión** con las credenciales de admin o un usuario creado.
2. **Panel principal:** Accede a la sección de especificaciones donde podrás:
   - Crear una nueva especificación seleccionando el tipo (Diseño Gráfico, Material de Empaque, Etiqueta, Etiqueta Zebra).
   - Completar el formulario dinámico con los datos técnicos.
   - Adjuntar imágenes de diseño (si el tipo lo requiere).
   - **Guardar como borrador** o **Publicar** (genera el PDF y lo almacena).
3. **Buscar especificaciones** por código, cliente o producto.
4. **Enviar por correo:** Desde el panel de un documento publicado, puedes encolar un envío a un destinatario. El worker procesará la cola respetando el rate limit configurado.
5. **Gestionar permisos:** Los administradores pueden otorgar permisos de edición, publicación o eliminación a otros usuarios sobre borradores específicos.

---

## 🔧 Variables de Entorno

| Variable | Descripción | Valor por Defecto |
|----------|-------------|-------------------|
| `ENVIOS_BURST` | Número máximo de envíos instantáneos permitidos en la cola. | `10` |
| `ENVIOS_INTERVALO_SEG` | Intervalo en segundos entre envíos después de agotar el burst. | `2.0` |
| `DRY_RUN` | Si es `1`, simula el envío de correos sin enviarlos realmente (útil para pruebas). | `0` |

---

## 🗄️ Base de Datos

El proyecto utiliza **SQLite** y las tablas principales son:

- `usuarios`: Almacena credenciales y roles.
- `especificaciones_generadas`: Documentos publicados con sus datos JSON y metadatos.
- `borradores`: Documentos en edición (no publicados).
- `envios_correo`: Cola y auditoría de envíos de correo.
- `contactos_correo`: Autocompletado de destinatarios.
- `permisos_globales` / `permisos_especificos`: Control de acceso granular.
- `notificaciones`: Mensajes internos para los usuarios.
- `permisos_usuario_seccion`: Acceso a secciones de la aplicación.

Puedes inspeccionar el esquema completo ejecutando:
```bash
python dump_schema.py
```

---

## 📄 Generación de PDFs

El flujo de generación de PDFs es el siguiente:

1. El usuario completa un formulario HTML.
2. Los datos se validan y se envían al backend.
3. Se renderiza una plantilla `.fodt` (OpenDocument) con los datos usando Jinja2.
4. La plantilla se convierte a PDF mediante **WeasyPrint** o **LibreOffice** (según la configuración).
5. El PDF se almacena y se registra en la base de datos con un código de revisión único.

Las imágenes adjuntas se procesan con **Pillow** para ajustarlas a los límites de tamaño definidos (`IMAGEN_ANCHO_MAX_CM`, `IMAGEN_ALTO_MAX_CM`).

---

## ✉️ Cola de Envíos de Correo

El módulo `envios_queue.py` implementa una **cola persistente** con las siguientes características:

- **Token bucket** para rate limiting (evita saturar el servidor de correo).
- **Worker en background** que procesa los envíos pendientes al iniciar la aplicación.
- **Persistencia:** los envíos se guardan en la tabla `envios_correo` con estados (`pendiente`, `enviando`, `enviado`, `error`).
- **Re-encolado automático** de envíos huérfanos al reiniciar el servidor.
- **Integración con Outlook** mediante `win32com` (requiere que Outlook esté instalado y configurado en la máquina donde corre la aplicación).

---

## 🤝 Contribuciones

Las contribuciones son bienvenidas. Si deseas mejorar el proyecto:

1. Haz un fork del repositorio.
2. Crea una rama para tu feature (`git checkout -b feature/nueva-funcionalidad`).
3. Realiza tus cambios y haz commit (`git commit -am 'Agrega nueva funcionalidad'`).
4. Haz push a la rama (`git push origin feature/nueva-funcionalidad`).
5. Abre un Pull Request.

---

## 📝 Licencia

Este proyecto está bajo la Licencia MIT. Consulta el archivo `LICENSE` para más detalles.

---

## 📧 Contacto

**Autor:** [matelopez1230](https://github.com/matelopez1230)  
**Repositorio:** [https://github.com/matelopez1230/empaque_v2](https://github.com/matelopez1230/empaque_v2)

---

> **Nota:** Este README fue generado a partir del análisis del código fuente y la estructura del repositorio. Si encuentras alguna discrepancia o deseas agregar más detalles, no dudes en actualizarlo.
