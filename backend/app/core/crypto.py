"""Xifrat aplicatiu AES-256-GCM (docs/06-seguretat.md §4).

Per a dades sensibles guardades a la BD (DNI, credencials de connectors).
Format del blob: 1 byte de versió de clau ‖ nonce (12) ‖ ciphertext+tag.
El byte de versió permet rotar ENCRYPTION_KEY sense re-xifrar-ho tot de cop.
"""

import base64
import os

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from app.core.config import settings

_KEY_VERSION = 1
_NONCE_SIZE = 12


class DecryptionError(Exception):
    pass


def _key() -> bytes:
    return base64.b64decode(settings.encryption_key.get_secret_value())


def encrypt_value(plaintext: str) -> bytes:
    nonce = os.urandom(_NONCE_SIZE)
    ciphertext = AESGCM(_key()).encrypt(nonce, plaintext.encode(), None)
    return bytes([_KEY_VERSION]) + nonce + ciphertext


def decrypt_value(blob: bytes) -> str:
    if len(blob) < 1 + _NONCE_SIZE or blob[0] != _KEY_VERSION:
        raise DecryptionError("Versió de clau desconeguda")
    nonce, ciphertext = blob[1 : 1 + _NONCE_SIZE], blob[1 + _NONCE_SIZE :]
    try:
        return AESGCM(_key()).decrypt(nonce, ciphertext, None).decode()
    except Exception as exc:
        raise DecryptionError("No es pot desxifrar el valor") from exc
