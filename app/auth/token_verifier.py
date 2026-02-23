import time
from dataclasses import dataclass
from typing import Any, Dict

import jwt
import requests
from flask import current_app
from jwt import PyJWKClient


class TokenVerificationError(Exception):
    pass


@dataclass
class CognitoIdentity:
    sub: str
    email: str | None
    claims: Dict[str, Any]


class CognitoTokenVerifier:
    def __init__(self, jwks_url: str, issuer: str, app_client_id: str, cache_ttl_seconds: int = 3600):
        self.jwks_url = jwks_url
        self.issuer = issuer
        self.app_client_id = app_client_id
        self.cache_ttl_seconds = cache_ttl_seconds
        self._cached_jwks = None
        self._cached_at = 0

    def _jwks_data(self):
        now = time.time()
        if self._cached_jwks and (now - self._cached_at) < self.cache_ttl_seconds:
            return self._cached_jwks

        resp = requests.get(self.jwks_url, timeout=5)
        resp.raise_for_status()
        self._cached_jwks = resp.json()
        self._cached_at = now
        return self._cached_jwks

    def verify(self, token: str) -> CognitoIdentity:
        try:
            jwks_client = PyJWKClient(self.jwks_url)
            jwks_client.fetch_data = self._jwks_data
            signing_key = jwks_client.get_signing_key_from_jwt(token)
            claims = jwt.decode(
                token,
                signing_key.key,
                algorithms=["RS256"],
                issuer=self.issuer,
                options={"verify_aud": False},
            )
        except Exception as exc:
            raise TokenVerificationError("Invalid Cognito token") from exc

        token_use = claims.get("token_use")
        if token_use == "id":
            aud = claims.get("aud")
            if aud != self.app_client_id:
                raise TokenVerificationError("Invalid audience")
        elif token_use == "access":
            client_id = claims.get("client_id")
            if client_id != self.app_client_id:
                raise TokenVerificationError("Invalid client id")
        else:
            raise TokenVerificationError("Invalid token_use")

        return CognitoIdentity(
            sub=claims.get("sub"),
            email=claims.get("email"),
            claims=claims,
        )


def get_cognito_verifier() -> CognitoTokenVerifier:
    cfg = current_app.config
    return CognitoTokenVerifier(
        jwks_url=cfg["COGNITO_JWKS_URL"],
        issuer=cfg["COGNITO_ISSUER"],
        app_client_id=cfg["COGNITO_APP_CLIENT_ID"],
        cache_ttl_seconds=cfg.get("COGNITO_JWKS_CACHE_SECONDS", 3600),
    )
