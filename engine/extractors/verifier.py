"""Adversarial verification: accept an enriched claim only if the source supports it."""
from __future__ import annotations

import json

from ..llm.ollama_client import ChatMessage

_SYSTEM = (
    "You are a strict fact-checker. Given SOURCE text and a set of keyed CLAIMS, decide for each "
    "claim whether the SOURCE EXPLICITLY supports it. Answer true ONLY if the source clearly states "
    "it; if the source does not clearly state it, answer false. Do NOT use outside knowledge. "
    "Return ONLY a JSON object mapping each claim key to true or false."
)


def verify_claims(claims: dict[str, str], source: str, *, ollama, model: str) -> dict[str, bool]:
    """Return {key: supported} for each claim. Missing/garbled answers default to False."""
    if not claims:
        return {}
    user = (
        f"SOURCE:\n{source[:14000]}\n\n"
        f"CLAIMS (json key -> statement):\n{json.dumps(claims)}\n\n"
        "Return a JSON object mapping each claim key to true or false."
    )
    raw = ollama.chat(
        model, [ChatMessage("system", _SYSTEM), ChatMessage("user", user)],
        temperature=0.0, json_mode=True,
    )
    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return {k: False for k in claims}
    if not isinstance(data, dict):
        return {k: False for k in claims}
    return {k: bool(data.get(k, False)) for k in claims}
