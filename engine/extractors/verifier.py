"""Adversarial verification: accept an enriched claim only if the source supports it."""
from __future__ import annotations

import json

from ..llm.ollama_client import ChatMessage

_SYSTEM = (
    "You are a STRICT, skeptical fact-checker. For each keyed CLAIM, decide whether the SOURCE "
    "text EXPLICITLY and SPECIFICALLY supports it about the named company/product. "
    "Answer true ONLY if the source clearly and directly states it. Answer FALSE if: it is merely "
    "implied; the source is a reseller/distributor/marketplace rather than the manufacturer; a "
    "country is only mentioned as a shipping, office, or reseller location without stating the "
    "company's OWN headquarters or country of origin; or you are unsure. When in doubt, answer "
    "false. Do NOT use outside knowledge. Return ONLY a JSON object mapping each claim key to "
    "true or false."
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
