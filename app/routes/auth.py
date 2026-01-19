from flask import Blueprint, request, jsonify
from app.models import User
from app.extensions import db
from flask_jwt_extended import create_access_token
from app.utils.rbac import require_active_user, get_current_user
from app.utils.audit import log_login, log_logout

auth_bp = Blueprint("auth", __name__)


# REGISTER (public - creates basic user account)
@auth_bp.post("/register")
def register():
    data = request.get_json()

    email = data.get("email", "").strip().lower()
    password = data.get("password", "")

    if not email or not password:
        return jsonify({"error": "Email and password are required"}), 400

    if len(password) < 8:
        return jsonify({"error": "Password must be at least 8 characters"}), 400

    if User.query.filter_by(email=email).first():
        return jsonify({"error": "Email already exists"}), 400

    user = User(email=email)
    user.set_password(password)

    db.session.add(user)
    db.session.commit()

    return jsonify({"message": "User created", "id": user.id}), 201


# LOGIN
@auth_bp.post("/login")
def login():
    data = request.get_json()

    email = data.get("email", "").strip().lower()
    password = data.get("password", "")

    if not email or not password:
        return jsonify({"error": "Email and password are required"}), 400

    user = User.query.filter_by(email=email).first()

    # Check credentials
    if not user or not user.check_password(password):
        # Log failed attempt (with email string, not user object)
        log_login(email, success=False)
        return jsonify({"error": "Invalid email or password"}), 401

    # Check if account is active
    if not user.is_active:
        log_login(email, success=False)
        return jsonify({
            "error": "Account is disabled. Contact an administrator.",
            "code": "ACCOUNT_DISABLED"
        }), 403

    # Create token and log success
    token = create_access_token(identity=str(user.id))
    log_login(user, success=True)

    return jsonify({
        "access_token": token,
        "user": user.to_dict()
    }), 200


# CURRENT USER
@auth_bp.get("/me")
@require_active_user
def me():
    user = request.current_user
    return jsonify(user.to_dict())


# LOGOUT (optional - mainly for audit logging)
@auth_bp.post("/logout")
@require_active_user
def logout():
    user = request.current_user
    log_logout(user)
    return jsonify({"message": "Logged out successfully"}), 200
