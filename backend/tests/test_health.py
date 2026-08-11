from fastapi.testclient import TestClient

from app.core.config import settings
from app.main import app

client = TestClient(app)


def test_health_returns_ok_and_version() -> None:
    response = client.get("/api/v1/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "version": settings.app_version}


def test_health_requires_no_auth_headers() -> None:
    # Endpoint públic per contracte (security: [] a openapi.yaml).
    response = client.get("/api/v1/health", headers={})

    assert response.status_code == 200


def test_openapi_docs_available() -> None:
    response = client.get("/docs")

    assert response.status_code == 200
