"""Entorn de test: secrets sintètics abans de qualsevol import de l'app.

Els tests no depenen del .env del desenvolupador: aquí es fixen els dos
secrets obligatoris amb valors vàlids només per a test.
"""

import base64
import os

os.environ.setdefault("SECRET_KEY", "test-secret-key-not-for-production-0123456789")
os.environ.setdefault("ENCRYPTION_KEY", base64.b64encode(b"\x00" * 32).decode())
os.environ.setdefault("ENVIRONMENT", "development")
