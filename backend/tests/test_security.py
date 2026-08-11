import uuid

import jwt
import pytest

from app.core.config import settings
from app.core.security import (
    InvalidAccessTokenError,
    create_access_token,
    decode_access_token,
    generate_refresh_token,
    hash_password,
    hash_refresh_token,
    verify_password,
)


def test_password_roundtrip() -> None:
    hashed = hash_password("Contrasenya-segura-123")

    assert hashed != "Contrasenya-segura-123"
    assert verify_password("Contrasenya-segura-123", hashed)
    assert not verify_password("una-altra", hashed)


def test_verify_against_missing_hash_is_false() -> None:
    # Usuari inexistent o LDAP: mai True, però tampoc excepció (timing uniforme).
    assert not verify_password("qualsevol", None)


def test_access_token_roundtrip() -> None:
    session_id = uuid.uuid4()
    token, expires_in = create_access_token(42, session_id)

    claims = decode_access_token(token)

    assert claims.user_id == 42
    assert claims.session_id == session_id
    assert expires_in == settings.access_token_expire_minutes * 60


def test_tampered_token_rejected() -> None:
    token, _ = create_access_token(42, uuid.uuid4())

    with pytest.raises(InvalidAccessTokenError):
        decode_access_token(token[:-2] + "xx")


def test_wrong_type_token_rejected() -> None:
    forged = jwt.encode(
        {"sub": "42", "sid": str(uuid.uuid4()), "type": "refresh", "iat": 0, "exp": 2**31},
        settings.secret_key.get_secret_value(),
        algorithm="HS256",
    )

    with pytest.raises(InvalidAccessTokenError):
        decode_access_token(forged)


def test_unsigned_token_rejected() -> None:
    forged = jwt.encode(
        {"sub": "42", "sid": str(uuid.uuid4()), "type": "access", "iat": 0, "exp": 2**31},
        "clau-incorrecta",
        algorithm="HS256",
    )

    with pytest.raises(InvalidAccessTokenError):
        decode_access_token(forged)


def test_refresh_token_hash_is_deterministic_and_opaque() -> None:
    token = generate_refresh_token()

    assert len(token) >= 43
    assert hash_refresh_token(token) == hash_refresh_token(token)
    assert token not in hash_refresh_token(token)
