"""Configuració centralitzada de l'aplicació.

Tots els valors venen de variables d'entorn (o d'un fitxer .env en
desenvolupament). Els secrets no tenen valor per defecte: si falten,
l'aplicació no arrenca.
"""

import base64
from typing import Literal

from pydantic import SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        # El .env viu a l'arrel del repositori; el segon path permet
        # sobreescriure en local des de backend/ si mai cal.
        env_file=("../.env", ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    environment: Literal["development", "staging", "production"] = "development"
    debug: bool = False
    app_version: str = "0.1.0"

    database_url: str = "postgresql+asyncpg://lagalia:lagalia@localhost:5432/lagalia"
    redis_url: str = "redis://localhost:6379/0"

    # Sense valor per defecte: obligatoris per arrencar.
    secret_key: SecretStr
    encryption_key: SecretStr

    access_token_expire_minutes: int = 30
    refresh_token_expire_days: int = 7

    cors_origins: list[str] = ["http://localhost:5173"]

    rate_limit_login: str = "5/minute"

    log_level: str = "INFO"
    log_format: Literal["json", "console"] = "json"

    @field_validator("secret_key")
    @classmethod
    def secret_key_is_strong(cls, value: SecretStr) -> SecretStr:
        if len(value.get_secret_value()) < 32:
            raise ValueError("SECRET_KEY ha de tenir almenys 32 caràcters")
        return value

    @field_validator("encryption_key")
    @classmethod
    def encryption_key_is_aes256(cls, value: SecretStr) -> SecretStr:
        try:
            raw = base64.b64decode(value.get_secret_value(), validate=True)
        except Exception as exc:
            raise ValueError("ENCRYPTION_KEY ha de ser base64 vàlid") from exc
        if len(raw) != 32:
            raise ValueError("ENCRYPTION_KEY ha de codificar exactament 32 bytes (AES-256)")
        return value


settings = Settings()
