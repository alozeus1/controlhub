from flask import Blueprint, render_template, jsonify

general_bp = Blueprint("general", __name__)

@general_bp.route("/")
def home():
    return render_template("index.html")

@general_bp.route("/healthz")
def healthz():
    return jsonify({"status": "ok"}), 200
