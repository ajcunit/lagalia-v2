"""Primitives d'autenticació: Argon2id, JWT d'accés i refresh tokens opacs.

Cap altra part del codi no fa servir jwt/argon2 directament.
"""

import hashlib
import secrets
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import VerificationError

from app.core.config import settings

_hasher = PasswordHasher()

# Hash fictici per igualar el temps de resposta quan l'usuari no existeix:
# sense això, la latència delataria quins correus tenen compte.
_DUMMY_HASH = _hasher.hash(secrets.token_urlsafe(24))


class InvalidAccessTokenError(Exception):
    pass


@dataclass(frozen=True)
class AccessClaims:
    user_id: int
    session_id: uuid.UUID


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password: str, password_hash: str | None) -> bool:
    """Verifica en temps constant respecte de l'existència de l'usuari."""
    try:
        _hasher.verify(password_hash or _DUMMY_HASH, password)
    except VerificationError:
        return False
    return password_hash is not None


def create_access_token(user_id: int, session_id: uuid.UUID) -> tuple[str, int]:
    """Retorna (token, expires_in en segons)."""
    expires_in = settings.access_token_expire_minutes * 60
    now = datetime.now(UTC)
    token = jwt.encode(
        {
            "sub": str(user_id),
            "sid": str(session_id),
            "type": "access",
            "iat": now,
            "exp": now + timedelta(seconds=expires_in),
        },
        settings.secret_key.get_secret_value(),
        algorithm="HS256",
    )
    return token, expires_in


def decode_access_token(token: str) -> AccessClaims:
    try:
        payload = jwt.decode(
            token,
            settings.secret_key.get_secret_value(),
            algorithms=["HS256"],
            options={"require": ["sub", "sid", "exp", "iat"]},
        )
    except jwt.InvalidTokenError as exc:
        raise InvalidAccessTokenError from exc
    if payload.get("type") != "access":
        raise InvalidAccessTokenError
    try:
        return AccessClaims(user_id=int(payload["sub"]), session_id=uuid.UUID(payload["sid"]))
    except (KeyError, ValueError) as exc:
        raise InvalidAccessTokenError from exc


def generate_refresh_token() -> str:
    return secrets.token_urlsafe(48)


def hash_refresh_token(token: str) -> str:
    # SHA-256 i no Argon2: el token ja és aleatori d'alta entropia i cal
    # poder-lo buscar per igualtat exacta a la BD.
    return hashlib.sha256(token.encode()).hexdigest()
