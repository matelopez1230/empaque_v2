# app.py
from flask import Flask, render_template, session, redirect, url_for

app = Flask(__name__)
app.secret_key = "cambia-esta-clave-por-una-larga-y-segura-2026"

# Blueprints
from auth import auth_bp
from routes_pdf import pdf_bp

app.register_blueprint(auth_bp)
app.register_blueprint(pdf_bp)


@app.route("/")
def index():
    if "user_id" not in session:
        return redirect(url_for("auth.login"))
    return redirect(url_for("pdf_generator.panel"))


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5001, debug=False)