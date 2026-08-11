import pytest

from app.core import crypto
from app.core.passwords import password_policy_errors


def test_encrypt_roundtrip() -> None:
    blob = crypto.encrypt_value("12345678Z")

    assert blob != b"12345678Z"
    assert crypto.decrypt_value(blob) == "12345678Z"


def test_encrypt_is_randomized() -> None:
    # GCM amb nonce aleatori: el mateix valor mai dona el mateix blob.
    assert crypto.encrypt_value("12345678Z") != crypto.encrypt_value("12345678Z")


def test_tampered_blob_fails() -> None:
    blob = bytearray(crypto.encrypt_value("12345678Z"))
    blob[-1] ^= 0xFF

    with pytest.raises(crypto.DecryptionError):
        crypto.decrypt_value(bytes(blob))


def test_unknown_key_version_fails() -> None:
    blob = b"\x99" + crypto.encrypt_value("x")[1:]

    with pytest.raises(crypto.DecryptionError):
        crypto.decrypt_value(blob)


@pytest.mark.parametrize(
    ("password", "valid"),
    [
        ("Contrasenya-Robusta-42", True),
        ("curta1A", False),  # menys de 12
        ("totminuscules123", False),  # sense majúscula
        ("TOTMAJUSCULES123", False),  # sense minúscula
        ("SenseCapXifraAqui", False),  # sense xifra
        ("Password12345", False),  # filtrada (case-insensitive)
    ],
)
def test_password_policy(password: str, valid: bool) -> None:
    errors = password_policy_errors(password)

    assert (not errors) is valid
