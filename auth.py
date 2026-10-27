# auth.py
from flask import (
    Blueprint, render_template, request, redirect,
    url_for, session, flash, jsonify,
)
from werkzeug.security import check_password_hash, generate_password_hash
from db import get_db_connection

auth_bp = Blueprint("auth", __name__)


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")

        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("""
            SELECT id, nombre, password_hash, es_admin
            FROM usuarios
            WHERE nombre = ? AND activo = 1
        """, (username,))
        user = cur.fetchone()
        conn.close()

        if user and check_password_hash(user["password_hash"], password):
            session["user_id"]  = user["id"]
            session["username"] = user["nombre"]
            session["es_admin"] = bool(user["es_admin"])
            return redirect(url_for("index"))

        flash("Usuario o contraseña incorrectos", "danger")

    return render_template("login.html")


@auth_bp.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("auth.login"))


@auth_bp.route("/cambiar-password", methods=["POST"])
def cambiar_password():
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"success": False, "error": "No autenticado"}), 401

    data = request.get_json() or {}
    actual = data.get("password_actual", "")
    nueva  = data.get("password_nueva", "")

    if not actual or not nueva:
        return jsonify({"success": False, "error": "Complete todos los campos"})
    if len(nueva) < 4:
        return jsonify({"success": False, "error": "Mínimo 4 caracteres"})

    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT password_hash FROM usuarios WHERE id = ?", (user_id,))
    row = cur.fetchone()

    if not row or not check_password_hash(row["password_hash"], actual):
        conn.close()
        return jsonify({"success": False, "error": "Contraseña actual incorrecta"})

    cur.execute(
        "UPDATE usuarios SET password_hash = ? WHERE id = ?",
        (generate_password_hash(nueva), user_id),
    )
    conn.commit()
    conn.close()
    return jsonify({"success": True, "mensaje": "Contraseña actualizada"})