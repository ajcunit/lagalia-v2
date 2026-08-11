"""Política de contrasenyes del contracte (openapi.yaml, schema Password).

Mínim 12 caràcters amb majúscula, minúscula i xifra, i rebuig de
contrasenyes presents en llistes de credencials filtrades (llista
embeguda de les més habituals; dataset complet: backlog B-008).
"""

# Subconjunt de les contrasenyes més freqüents en filtracions públiques
# que compleixen (o quasi) els requisits de forma — les que no els
# compleixen ja cauen per les altres regles.
_LEAKED_PASSWORDS = frozenset(
    {
        "password1234",
        "password12345",
        "password123456",
        "passw0rd1234",
        "p@ssw0rd1234",
        "administrator1",
        "administrador1",
        "contrasenya123",
        "contrasena1234",
        "qwertyuiop123",
        "1q2w3e4r5t6y7u",
        "abcd1234abcd",
        "welcome12345",
        "benvingut1234",
        "barcelona1234",
        "iloveyou1234",
        "superman1234",
        "1234567890ab",
        "aa123456789012",
        "letmein12345",
    }
)


def password_policy_errors(password: str) -> list[str]:
    """Retorna la llista de motius pels quals la contrasenya no és vàlida."""
    errors: list[str] = []
    if len(password) < 12:
        errors.append("ha de tenir com a mínim 12 caràcters")
    if not any(c.isupper() for c in password):
        errors.append("ha d'incloure alguna majúscula")
    if not any(c.islower() for c in password):
        errors.append("ha d'incloure alguna minúscula")
    if not any(c.isdigit() for c in password):
        errors.append("ha d'incloure alguna xifra")
    if password.lower() in _LEAKED_PASSWORDS:
        errors.append("apareix en llistes de credencials filtrades")
    return errors
