from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from flask_jwt_extended import JWTManager
try:
    from flask_limiter import Limiter
    from flask_limiter.util import get_remote_address
except ImportError:
    Limiter = None
    get_remote_address = lambda: "0.0.0.0"

try:
    from flask_mail import Mail
except ImportError:
    Mail = None

db = SQLAlchemy()
migrate = Migrate()
jwt = JWTManager()


class _NoopMail:
    def init_app(self, app):
        return None

    def send(self, message):
        return None


class _NoopLimiter:
    _storage_uri = None

    def init_app(self, app):
        return None

    def limit(self, *_args, **_kwargs):
        def decorator(fn):
            return fn
        return decorator


mail = Mail() if Mail is not None else _NoopMail()
limiter = (
    Limiter(
        key_func=get_remote_address,
        default_limits=[],
        storage_uri=None,  # Set at app init from config
    )
    if Limiter is not None
    else _NoopLimiter()
)
