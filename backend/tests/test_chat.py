import os
from types import SimpleNamespace

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


def test_chat_stream_emits_progress_and_final_response(monkeypatch) -> None:
    def fake_iter_reply_events(self, messages, system_prompt=None):
        yield {"type": "status", "message": "Analisando pedido."}
        yield {"type": "tool_started", "index": 1, "name": "wake_pc", "args": {}}
        yield {"type": "tool_finished", "index": 1, "name": "wake_pc", "args": {}, "summary": "PC ligado."}
        yield {
            "type": "reply_finished",
            "assistant_text": "PC ligado.",
            "openai_response_id": "resp_stream",
            "tool_calls": [{"name": "wake_pc", "args": {}}],
        }

    monkeypatch.setattr(OpenAIChatService, "iter_reply_events", fake_iter_reply_events)
    monkeypatch.setattr(OpenAIChatService, "model", property(lambda self: "test-model"))

    with TestClient(app) as test_client:
        with test_client.stream("POST", "/api/v1/chat/stream", json={"message": "ligue meu pc"}) as response:
            body = response.read().decode("utf-8")

        assert response.status_code == 200
        assert "text/event-stream" in response.headers["content-type"]
        assert '"type": "user_message"' in body
        assert '"type": "tool_started"' in body
        assert '"type": "tool_finished"' in body
        assert '"type": "final"' in body
        assert "PC ligado." in body


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
    assert "Modo operacional" in captured["input"][0]["content"]
    assert captured["tools"]


def test_openai_service_continues_through_multiple_tool_rounds(monkeypatch) -> None:
    from app.services import openai_chat_service

    executed = []

    def fake_execute_tool(name, args):
        executed.append((name, args))
        return f"resultado de {name}"

    class FakeResponses:
        def __init__(self):
            self.calls = []

        def create(self, model, input, tools=None, previous_response_id=None):
            self.calls.append({"input": input, "previous_response_id": previous_response_id})
            index = len(self.calls)
            if index == 1:
                return SimpleNamespace(
                    id="resp_1",
                    output_text="",
                    output=[
                        SimpleNamespace(type="function_call", name="wake_pc", arguments="{}", call_id="call_1")
                    ],
                )
            if index == 2:
                assert input[0]["type"] == "function_call_output"
                assert input[0]["call_id"] == "call_1"
                return SimpleNamespace(
                    id="resp_2",
                    output_text="",
                    output=[
                        SimpleNamespace(
                            type="function_call",
                            name="run_command",
                            arguments='{"command":"dir C:\\\\Users\\\\luigi\\\\Documents /b"}',
                            call_id="call_2",
                        )
                    ],
                )
            assert input[0]["type"] == "function_call_output"
            assert input[0]["call_id"] == "call_2"
            return SimpleNamespace(id="resp_3", output_text="Fluxo concluido.", output=[])

    class FakeClient:
        def __init__(self):
            self.responses = FakeResponses()

    service = OpenAIChatService()
    service.client = FakeClient()
    monkeypatch.setattr(service.settings, "openai_api_key", "test-key")
    monkeypatch.setattr(openai_chat_service, "_execute_tool", fake_execute_tool)

    assistant_text, response_id, tool_calls = service.generate_reply(messages=[])

    assert assistant_text == "Fluxo concluido."
    assert response_id == "resp_3"
    assert [call["name"] for call in tool_calls] == ["wake_pc", "run_command"]
    assert executed == [
        ("wake_pc", {}),
        ("run_command", {"command": "dir C:\\Users\\luigi\\Documents /b"}),
    ]
    assert len(service.client.responses.calls) == 3
