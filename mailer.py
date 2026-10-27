# mailer.py — Versión local con Outlook (Windows)
import os
import win32com.client

DRY_RUN = os.environ.get("DRY_RUN", "0") == "1"

class MailError(Exception):
    pass

def enviar_pdf(destinatario, pdf_bytes, nombre_archivo, asunto, cuerpo,
               from_addr=None, from_name=None, reply_to=None):
    if not destinatario or "@" not in destinatario:
        raise MailError("Destinatario inválido")

    if DRY_RUN:
        print(f"[DRY-RUN] Outlook → Para: {destinatario} | Adjunto: {nombre_archivo}")
        return True

    try:
        # Conectar con la instancia de Outlook abierta en la PC
        outlook = win32com.client.Dispatch("Outlook.Application")
        mail = outlook.CreateItem(0) # 0 = MailItem

        mail.To = destinatario
        mail.Subject = asunto
        mail.Body = cuerpo or "Adjunto encontrará la especificación solicitada."

        # Para adjuntar desde memoria sin guardar en disco, 
        # Outlook requiere que el archivo exista temporalmente.
        import tempfile
        with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
            tmp.write(pdf_bytes)
            tmp_path = tmp.name

        mail.Attachments.Add(tmp_path)
        
        # Enviar
        mail.Send()
        
        # Limpiar el archivo temporal
        os.remove(tmp_path)

    except Exception as e:
        raise MailError(f"Error al usar Outlook: {str(e)}")

    return True