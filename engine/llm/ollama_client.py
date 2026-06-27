"""Minimal Ollama chat client over httpx. Injectable transport for testing."""
from __future__ import annotations

from dataclasses import dataclass

import httpx


@dataclass
class ChatMessage:
    role: str
    content: str


class OllamaClient:
    def __init__(
        self,
        host: str = "http://localhost:11434",
        *,
        timeout: float = 120.0,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self._client = httpx.Client(
            base_url=host.rstrip("/"), timeout=timeout, transport=transport
        )

    def __enter__(self) -> "OllamaClient":
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def close(self) -> None:
        self._client.close()

    def chat(
        self,
        model: str,
        messages: list[ChatMessage],
        *,
        temperature: float = 0.2,
        json_mode: bool = False,
    ) -> str:
        payload: dict = {
            "model": model,
            "messages": [{"role": m.role, "content": m.content} for m in messages],
            "stream": False,
            "options": {"temperature": temperature},
        }
        if json_mode:
            payload["format"] = "json"
        resp = self._client.post("/api/chat", json=payload)
        resp.raise_for_status()
        return resp.json()["message"]["content"]

    def ping(self, model: str) -> bool:
        try:
            return bool(self.chat(model, [ChatMessage("user", "reply: ok")], temperature=0))
        except Exception:
            return False
