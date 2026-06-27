"""Extract a structured Controller record from source text via the LLM."""
from __future__ import annotations

import json
import re

from pydantic import ValidationError

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
    "vendor, model, sku (exact model/part number e.g. UC300-L05EU — NOT price or marketing text), "
    "country_of_origin, cellular (bool), cellular_tech, wifi (bool), "
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
_MAX_CHARS = 24000


def build_messages(text: str) -> list[ChatMessage]:
    user = (
        f"Extract the controller spec. Return JSON with these keys (null if unknown):\n{_KEYS}\n\n"
        f"TEXT:\n{text[:_MAX_CHARS]}"
    )
    return [ChatMessage("system", _SYSTEM), ChatMessage("user", user)]


def _validate_salvage(data: dict) -> Controller | None:
    """Validate into a Controller, dropping individual fields that fail rather
    than discarding the whole (otherwise-good) record. Bounded retries."""
    for _ in range(8):
        try:
            return Controller.model_validate(data)
        except ValidationError as exc:
            removed = False
            for err in exc.errors():
                loc = err["loc"]
                if not loc:
                    continue
                top = loc[0]
                if len(loc) >= 2 and isinstance(data.get(top), dict):
                    if loc[1] in data[top]:
                        data[top].pop(loc[1], None)
                        removed = True
                elif top in data:
                    data.pop(top, None)
                    removed = True
            if not removed:
                return None
    return None


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
    # Infer api_type from the protocols list when the model left it unknown.
    if data.get("api_type", "unknown") == "unknown":
        protos = " ".join(str(p) for p in (data.get("protocols") or [])).lower()
        if "mqtt" in protos:
            data["api_type"] = "native_mqtt"
        elif "rest" in protos or "http api" in protos:
            data["api_type"] = "rest_http"
    # An open protocol implies the buyer can point it at their own broker/server.
    if data.get("own_broker") is None and data.get("api_type") in ("native_mqtt", "rest_http"):
        data["own_broker"] = True
    # Drop junk SKUs (the model sometimes grabs price/marketing text).
    sku = data.get("sku")
    if isinstance(sku, str) and (
        len(sku) > 40 or any(t in sku.lower() for t in ("vat", "€", "eur ", "price", "incl.", "excl."))
    ):
        data["sku"] = None
    if source_url:
        sources = data.get("sources") or []
        if source_url not in sources:
            sources.append(source_url)
        data["sources"] = sources
    return _validate_salvage(data)
