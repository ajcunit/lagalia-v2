import base64

import pytest
from pydantic import ValidationError

from app.core.config import Settings

VALID_ENCRYPTION_KEY = base64.b64encode(b"\x01" * 32).decode()
VALID_SECRET_KEY = "prou-llarga-per-passar-la-validacio-0123456789"


def _settings(**overrides: str) -> Settings:
    values = {
        "secret_key": VALID_SECRET_KEY,
        "encryption_key": VALID_ENCRYPTION_KEY,
        **overrides,
    }
    return Settings(_env_file=None, **values)  # type: ignore[arg-type]


def test_fails_without_secret_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("SECRET_KEY", raising=False)

    with pytest.raises(ValidationError, match="secret_key"):
        Settings(_env_file=None, encryption_key=VALID_ENCRYPTION_KEY)


def test_fails_without_encryption_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ENCRYPTION_KEY", raising=False)

    with pytest.raises(ValidationError, match="encryption_key"):
        Settings(_env_file=None, secret_key=VALID_SECRET_KEY)


def test_fails_with_short_secret_key() -> None:
    with pytest.raises(ValidationError, match="32"):
        _settings(secret_key="curta")


def test_fails_with_non_base64_encryption_key() -> None:
    with pytest.raises(ValidationError, match="base64"):
        _settings(encryption_key="això-no-és-base64!!!")


def test_fails_with_wrong_length_encryption_key() -> None:
    with pytest.raises(ValidationError, match="32 bytes"):
        _settings(encryption_key=base64.b64encode(b"\x01" * 16).decode())


def test_defaults_are_safe() -> None:
    settings = _settings()

    assert settings.environment == "development"
    assert settings.debug is False
    assert settings.log_format == "json"


def test_secrets_never_leak_in_repr() -> None:
    settings = _settings()

    assert VALID_SECRET_KEY not in repr(settings)
    assert VALID_ENCRYPTION_KEY not in repr(settings)
