import datetime
import jwt
from flask import current_app, request
from functools import wraps
from app.models import User

def generate_jwt(user):
    payload = {
        "user_id": user.id,
        "exp": datetime.datetime.utcnow() + datetime.timedelta(hours=12)
    }
    return jwt.encode(payload, current_app.config["SECRET_KEY"], algorithm="HS256")

def decode_jwt(token):
    try:
        return jwt.decode(token, current_app.config["SECRET_KEY"], algorithms=["HS256"])
    except:
        return None

def jwt_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        token = None

        # JWT must be in Authorization header
        if "Authorization" in request.headers:
            token = request.headers["Authorization"].split(" ")[1]

        if not token:
            return {"error": "Missing token"}, 401

        data = decode_jwt(token)
        if not data:
            return {"error": "Invalid or expired token"}, 401

        user = User.query.get(data["user_id"])
        if not user:
            return {"error": "User no longer exists"}, 401

        # Attach user to request context
        request.user = user
        return f(*args, **kwargs)

    return wrapper
