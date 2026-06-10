import os

os.environ["DATABASE_URL"] = "sqlite:///:memory:"

from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.main import app


client = TestClient(app)


def test_health_check(monkeypatch) -> None:
    settings = get_settings()
    monkeypatch.setattr(settings, "app_env", "development")

    response = client.get("/api/v1/health")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "service": "walt-agent",
        "environment": "development",
    }
