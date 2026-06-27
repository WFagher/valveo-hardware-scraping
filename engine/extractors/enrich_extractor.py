"""LLM extraction of sourcing/compliance fields (OEM, CE/RED, origin, rebrand)."""
from __future__ import annotations

import json

from ..llm.ollama_client import ChatMessage

_SYSTEM = (
    "You research a product's sourcing and compliance facts from the text provided. "
    "Return ONLY a JSON object. Use null for anything NOT stated in the text — never invent."
)

_KEYS = (
    "country_of_origin (where the VENDOR is based/headquartered), ce (bool), red (bool), "
    "oem_offered (bool: does the vendor offer OEM / white-label / private-label / ODM?), "
    "oem_moq (int minimum order quantity if stated), "
    "rebrand_path (choose ONE of oem_program, resell_as_is, recase_diy, none, unknown)"
)


def build_enrich_messages(text: str) -> list[ChatMessage]:
    user = (
        f"Extract these keys (null if not stated):\n{_KEYS}\n\nTEXT:\n{text[:16000]}"
    )
    return [ChatMessage("system", _SYSTEM), ChatMessage("user", user)]


def extract_enrichment(text: str, *, ollama, model: str) -> dict:
    raw = ollama.chat(model, build_enrich_messages(text), temperature=0.1, json_mode=True)
    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return {}
    return data if isinstance(data, dict) else {}
