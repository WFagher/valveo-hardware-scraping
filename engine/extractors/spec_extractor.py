"""Extract a structured Controller record from source text via the LLM."""
from __future__ import annotations

import json
import re

from ..llm.ollama_client import ChatMessage
from ..models import ApiType, Controller, Programmability

_VALID_API = {e.value for e in ApiType}
_VALID_PROG = {e.value for e in Programmability}

_SYSTEM = (
    "You extract the specs of a cellular door-access controller from the text provided. "
    "Fill ONLY the requested JSON keys. Use null for anything NOT explicitly stated in the "
    "text — never invent a value. Return ONLY a JSON object, no prose."
)

_KEYS = (
    "vendor, model, sku, country_of_origin, cellular (bool), cellular_tech, wifi (bool), "
    "bluetooth (bool), ethernet (bool), "
    "api_type (choose ONE of native_mqtt, rest_http, vendor_cloud_only, unknown), "
    "protocols (list of strings), "
    "programmability (choose ONE of config_only, rules_engine, sdk_required, unknown), "
    "own_broker (bool), digital_inputs (int), ip_rating, price_eur (number), "
    "lock (object: relay_count int, relay_rating), "
    "reader (object: wiegand, osdp, rs485, rs232 booleans), "
    "cert (object: ce, red booleans)"
)


# Cap source text so a noisy page doesn't blow up prompt-processing time on a local model.
_MAX_CHARS = 16000


def build_messages(text: str) -> list[ChatMessage]:
    user = (
        f"Extract the controller spec. Return JSON with these keys (null if unknown):\n{_KEYS}\n\n"
        f"TEXT:\n{text[:_MAX_CHARS]}"
    )
    return [ChatMessage("system", _SYSTEM), ChatMessage("user", user)]


def _coerce_enum(value: object, valid: set[str], default: str) -> str:
    """Map a model-returned string to a valid enum value.

    Handles the model echoing the option list (e.g. 'native_mqtt|rest_http') by
    taking the first valid token, instead of dropping the whole record.
    """
    if isinstance(value, str):
        if value in valid:
            return value
        for token in re.split(r"[|,/]", value):
            token = token.strip()
            if token in valid:
                return token
    return default


def _strip_fences(s: str) -> str:
    s = s.strip()
    if s.startswith("```"):
        s = s.strip("`")
        if s.lower().startswith("json"):
            s = s[4:]
    return s.strip()


def extract_controller(
    text: str, *, ollama, model: str, source_url: str | None = None
) -> Controller | None:
    raw = ollama.chat(model, build_messages(text), temperature=0.1, json_mode=True)
    try:
        data = json.loads(_strip_fences(raw))
    except (json.JSONDecodeError, TypeError):
        return None
    if not isinstance(data, dict) or not data.get("vendor") or not data.get("model"):
        return None
    if "api_type" in data:
        data["api_type"] = _coerce_enum(data["api_type"], _VALID_API, "unknown")
    if "programmability" in data:
        data["programmability"] = _coerce_enum(data["programmability"], _VALID_PROG, "unknown")
    if source_url:
        sources = data.get("sources") or []
        if source_url not in sources:
            sources.append(source_url)
        data["sources"] = sources
    try:
        return Controller.model_validate(data)
    except Exception:
        return None
