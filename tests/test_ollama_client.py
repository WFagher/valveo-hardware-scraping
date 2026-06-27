from __future__ import annotations

import httpx

from engine.llm.ollama_client import ChatMessage, OllamaClient


def _transport(captured):
    def handler(request):
        captured["payload"] = request.content
        return httpx.Response(200, json={"message": {"content": "hello"}})

    return httpx.MockTransport(handler)


def test_chat_returns_message_content():
    cap = {}
    with OllamaClient(transport=_transport(cap)) as ol:
        out = ol.chat("m", [ChatMessage("user", "hi")], json_mode=True)
    assert out == "hello"
    assert b'"format": "json"' in cap["payload"] or b'"format":"json"' in cap["payload"]


def test_ping_true_on_response():
    with OllamaClient(transport=_transport({})) as ol:
        assert ol.ping("m") is True


def test_ping_false_on_error():
    def handler(request):
        return httpx.Response(500, json={})

    with OllamaClient(transport=httpx.MockTransport(handler)) as ol:
        assert ol.ping("m") is False
