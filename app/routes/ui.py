from flask import Blueprint, render_template, request, redirect, session
import requests
from flask import current_app

ui_bp = Blueprint("ui", __name__)

API_BASE = "http://localhost:9000"

@ui_bp.route("/login", methods=["GET", "POST"])
def login_page():
    if request.method == "POST":
        data = {
            "email": request.form["email"],
            "password": request.form["password"]
        }

        r = requests.post(f"{API_BASE}/auth/login", json=data)
        if r.status_code == 200:
            token = r.json()["access_token"]
            session["jwt"] = token
            return redirect("/ui/admin")
        return "Invalid login", 401

    return render_template("login.html")


@ui_bp.route("/admin")
def admin_home():
    return render_template("admin/index.html")


@ui_bp.route("/admin/users")
def admin_users():
    token = session.get("jwt")
    r = requests.get(f"{API_BASE}/admin/users",
                     headers={"Authorization": f"Bearer {token}"})
    return render_template("admin/users.html", users=r.json())


@ui_bp.route("/admin/uploads")
def admin_uploads():
    token = session.get("jwt")
    r = requests.get(f"{API_BASE}/admin/uploads",
                     headers={"Authorization": f"Bearer {token}"})
    return render_template("admin/uploads.html", uploads=r.json())


@ui_bp.route("/admin/jobs")
def admin_jobs():
    token = session.get("jwt")
    r = requests.get(f"{API_BASE}/admin/jobs",
                     headers={"Authorization": f"Bearer {token}"})
    return render_template("admin/jobs.html", jobs=r.json())
