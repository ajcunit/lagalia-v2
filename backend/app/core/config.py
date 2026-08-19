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
    # Cua d'arq. Els tests en fan servir una de pròpia perquè un worker viu
    # de desenvolupament no executi els jobs que encuen.
    jobs_queue_name: str = "arq:queue"

    # Sense valor per defecte: obligatoris per arrencar.
    secret_key: SecretStr
    encryption_key: SecretStr

    access_token_expire_minutes: int = 30
    refresh_token_expire_days: int = 7

    cors_origins: list[str] = ["http://localhost:5173"]

    rate_limit_login: str = "5/minute"

    # Emmagatzematge d'objectes (B-003: la tria és configuració).
    # CA bundle per a destins interns amb certificat propi (webhooks n8n...).
    # La verificació TLS no es desactiva MAI (06 §2): fitxer PEM amb les CA
    # públiques més la interna.
    outbound_ca_bundle: str | None = None

    storage_backend: Literal["filesystem", "s3"] = "filesystem"
    storage_local_path: str = "./storage"
    s3_endpoint_url: str = "http://localhost:9000"
    s3_bucket: str = "lagalia"
    s3_access_key: SecretStr = SecretStr("")
    s3_secret_key: SecretStr = SecretStr("")

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
