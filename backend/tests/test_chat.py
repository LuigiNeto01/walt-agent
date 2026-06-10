import os

os.environ["DATABASE_URL"] = "sqlite:///:memory:"

from fastapi.testclient import TestClient

from app.main import app
from app.services.chat_service import _build_title
from app.services.openai_chat_service import OpenAIChatService


def test_chat_message_is_saved_with_assistant_reply(monkeypatch) -> None:
    def fake_generate_reply(self, messages, system_prompt=None) -> tuple[str, str, list[dict]]:
        return "Resposta simulada", "resp_test", []

    monkeypatch.setattr(OpenAIChatService, "generate_reply", fake_generate_reply)
    monkeypatch.setattr(OpenAIChatService, "model", property(lambda self: "test-model"))

    with TestClient(app) as test_client:
        response = test_client.post("/api/v1/chat", json={"message": "Oi"})

        assert response.status_code == 201
        payload = response.json()
        conversation_id = payload["conversation"]["id"]
        assert payload["user_message"]["content"] == "Oi"
        assert payload["assistant_message"]["content"] == "Resposta simulada"

        messages_response = test_client.get(f"/api/v1/chat/conversations/{conversation_id}/messages")
        assert messages_response.status_code == 200
        assert [message["role"] for message in messages_response.json()] == ["user", "assistant"]


def test_delete_chat_conversation_removes_it(monkeypatch) -> None:
    def fake_generate_reply(self, messages, system_prompt=None) -> tuple[str, str, list[dict]]:
        return "Resposta simulada", "resp_test", []

    monkeypatch.setattr(OpenAIChatService, "generate_reply", fake_generate_reply)
    monkeypatch.setattr(OpenAIChatService, "model", property(lambda self: "test-model"))

    with TestClient(app) as test_client:
        response = test_client.post("/api/v1/chat", json={"message": "Apagar depois"})
        conversation_id = response.json()["conversation"]["id"]

        delete_response = test_client.delete(f"/api/v1/chat/conversations/{conversation_id}")
        assert delete_response.status_code == 204

        messages_response = test_client.get(f"/api/v1/chat/conversations/{conversation_id}/messages")
        assert messages_response.status_code == 404


def test_chat_title_summarizes_first_message() -> None:
    title = _build_title("quero que crie um frontend em reactjs para essa aplicacao")

    assert title == "Crie frontend reactjs aplicacao"


def test_chat_persists_tool_calls(monkeypatch) -> None:
    def fake_generate_reply(self, messages, system_prompt=None) -> tuple[str, str, list[dict]]:
        return "Liguei o PC.", "resp_test", [{"name": "wake_pc", "args": {}}]

    monkeypatch.setattr(OpenAIChatService, "generate_reply", fake_generate_reply)
    monkeypatch.setattr(OpenAIChatService, "model", property(lambda self: "test-model"))

    with TestClient(app) as test_client:
        response = test_client.post("/api/v1/chat", json={"message": "ligue meu pc"})

        assert response.status_code == 201
        assistant = response.json()["assistant_message"]
        assert assistant["tool_calls_json"] == '[{"name": "wake_pc", "args": {}}]'


def test_openai_service_uses_default_system_prompt(monkeypatch) -> None:
    captured = {}

    class FakeResponses:
        def create(self, model, input, tools=None):
            captured["input"] = input
            captured["tools"] = tools

            class FakeResponse:
                output_text = "Oi, sou Walt."
                id = "resp_test"
                output = []

            return FakeResponse()

    class FakeClient:
        responses = FakeResponses()

    from app.services.openai_chat_service import OpenAIChatService

    service = OpenAIChatService()
    service.client = FakeClient()
    monkeypatch.setattr(service.settings, "openai_api_key", "test-key")

    service.generate_reply(messages=[])

    assert captured["input"][0]["role"] == "system"
    assert "Voce se chama Walt" in captured["input"][0]["content"]
    assert captured["tools"]
