from fastapi.testclient import TestClient

from app.main import app


from app.core.config import get_settings


def test_wake_pc_returns_configuration_message_when_disabled(monkeypatch) -> None:
    settings = get_settings()
    monkeypatch.setattr(settings, "wake_on_lan_enabled", False)

    with TestClient(app) as client:
        response = client.post("/api/v1/tools/wake-pc")

    assert response.status_code == 200
    assert response.json()["ok"] is False
    assert "WAKE_ON_LAN_ENABLED=true" in response.json()["message"]


def test_ssh_run_returns_configuration_message_when_disabled(monkeypatch) -> None:
    settings = get_settings()
    monkeypatch.setattr(settings, "ssh_enabled", False)

    with TestClient(app) as client:
        response = client.post("/api/v1/tools/ssh/run", json={"command": "hostname"})

    assert response.status_code == 200
    assert response.json()["ok"] is False
    assert "SSH_ENABLED=true" in response.json()["message"]


def test_ssh_read_file_returns_configuration_message_when_disabled(monkeypatch) -> None:
    settings = get_settings()
    monkeypatch.setattr(settings, "ssh_enabled", False)

    with TestClient(app) as client:
        response = client.post("/api/v1/tools/ssh/read-file", json={"path": "C:\\Temp\\a.txt"})

    assert response.status_code == 200
    assert response.json()["ok"] is False
    assert "SSH_ENABLED=true" in response.json()["message"]


def test_ssh_python_returns_configuration_message_when_disabled(monkeypatch) -> None:
    settings = get_settings()
    monkeypatch.setattr(settings, "ssh_enabled", False)

    with TestClient(app) as client:
        response = client.post("/api/v1/tools/ssh/python", json={"code": "print('oi')"})

    assert response.status_code == 200
    assert response.json()["ok"] is False
    assert "SSH_ENABLED=true" in response.json()["message"]
