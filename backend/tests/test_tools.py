from fastapi.testclient import TestClient

from app.main import app


from app.core.config import get_settings
from app.services.wake_on_lan_service import send_wake_on_lan_packet


def test_wake_pc_returns_configuration_message_when_disabled(monkeypatch) -> None:
    settings = get_settings()
    monkeypatch.setattr(settings, "wake_on_lan_enabled", False)

    with TestClient(app) as client:
        response = client.post("/api/v1/tools/wake-pc")

    assert response.status_code == 200
    assert response.json()["ok"] is False
    assert "WAKE_ON_LAN_ENABLED=true" in response.json()["message"]


def test_wake_pc_binds_to_configured_source_ip(monkeypatch) -> None:
    settings = get_settings()
    monkeypatch.setattr(settings, "wake_on_lan_enabled", True)
    monkeypatch.setattr(settings, "wake_target_mac", "30:56:0F:5C:A9:3A")
    monkeypatch.setattr(settings, "wake_broadcast_ip", "192.168.0.255")
    monkeypatch.setattr(settings, "wake_source_ip", "192.168.0.4")
    monkeypatch.setattr(settings, "wake_port", 9)
    monkeypatch.setattr(settings, "ssh_enabled", False)

    calls: dict[str, object] = {}

    class FakeSocket:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def setsockopt(self, level, option, value):
            calls["setsockopt"] = (level, option, value)

        def bind(self, address):
            calls["bind"] = address

        def sendto(self, packet, address):
            calls["packet"] = packet
            calls["sendto"] = address

    monkeypatch.setattr("app.services.wake_on_lan_service.socket.socket", lambda *args, **kwargs: FakeSocket())

    response = send_wake_on_lan_packet()

    assert response.ok is True
    assert response.source_ip == "192.168.0.4"
    assert "192.168.0.4" in response.message
    assert calls["bind"] == ("192.168.0.4", 0)
    assert calls["sendto"] == ("192.168.0.255", 9)
    assert len(calls["packet"]) == 102


def test_wake_pc_falls_back_when_source_ip_is_unavailable(monkeypatch) -> None:
    settings = get_settings()
    monkeypatch.setattr(settings, "wake_on_lan_enabled", True)
    monkeypatch.setattr(settings, "wake_target_mac", "30:56:0F:5C:A9:3A")
    monkeypatch.setattr(settings, "wake_broadcast_ip", "192.168.0.255")
    monkeypatch.setattr(settings, "wake_source_ip", "192.168.0.4")
    monkeypatch.setattr(settings, "wake_port", 9)
    monkeypatch.setattr(settings, "ssh_enabled", False)

    calls: dict[str, object] = {}

    class FakeSocket:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def setsockopt(self, level, option, value):
            calls["setsockopt"] = (level, option, value)

        def bind(self, address):
            calls["bind"] = address
            raise OSError(99, "Cannot assign requested address")

        def sendto(self, packet, address):
            calls["packet"] = packet
            calls["sendto"] = address

    monkeypatch.setattr("app.services.wake_on_lan_service.socket.socket", lambda *args, **kwargs: FakeSocket())

    response = send_wake_on_lan_packet()

    assert response.ok is True
    assert response.source_ip is None
    assert "envio seguiu sem bind explicito" in response.message
    assert calls["bind"] == ("192.168.0.4", 0)
    assert calls["sendto"] == ("192.168.0.255", 9)


def test_wake_pc_reports_when_ssh_becomes_ready(monkeypatch) -> None:
    settings = get_settings()
    monkeypatch.setattr(settings, "wake_on_lan_enabled", True)
    monkeypatch.setattr(settings, "wake_target_mac", "30:56:0F:5C:A9:3A")
    monkeypatch.setattr(settings, "wake_broadcast_ip", "192.168.0.255")
    monkeypatch.setattr(settings, "wake_source_ip", None)
    monkeypatch.setattr(settings, "wake_port", 9)
    monkeypatch.setattr(settings, "ssh_enabled", True)
    monkeypatch.setattr(settings, "ssh_host", "192.168.0.4")
    monkeypatch.setattr(settings, "ssh_port", 22)
    monkeypatch.setattr(settings, "wake_verify_ssh_timeout", 10)
    monkeypatch.setattr(settings, "wake_verify_ssh_interval", 1)

    class FakeSocket:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def setsockopt(self, level, option, value):
            pass

        def sendto(self, packet, address):
            pass

    class FakeConnection:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

    connect_calls = []

    def fake_create_connection(address, timeout=None):
        connect_calls.append((address, timeout))
        return FakeConnection()

    monkeypatch.setattr("app.services.wake_on_lan_service.socket.socket", lambda *args, **kwargs: FakeSocket())
    monkeypatch.setattr("app.services.wake_on_lan_service.socket.create_connection", fake_create_connection)

    response = send_wake_on_lan_packet()

    assert response.ok is True
    assert response.ssh_ready is True
    assert "SSH respondeu" in response.message
    assert connect_calls == [(("192.168.0.4", 22), 1)]


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
