"""Per-device deep-dive report (spec 2.1): structured facts + LLM prose."""
from __future__ import annotations

import json

from ..llm.ollama_client import ChatMessage
from ..models import ApiType, Controller, Programmability

_ANALYSIS_KEYS = ("scenarios", "limitations", "mitigations", "verdict")


def variant_warning(c: Controller) -> str | None:
    name = f"{c.model} {c.sku or ''}".lower()
    if "uc300" in name:
        return (
            "Milesight UC300 ships as LoRaWAN (`-470M/868M/915M`) **or** Cellular (`-L0xx`). "
            "Only the Cellular `-L0xx` SKU qualifies — never order an `-868M`."
        )
    return None


def _has_reader(c: Controller) -> bool:
    return c.reader.wiegand or c.reader.osdp or c.reader.rs485 or c.reader.native_reader


def criteria_fit_rows(c: Controller, requirements: dict) -> list[tuple[str, bool, str]]:
    relay_min = requirements.get("hard", {}).get("relay_min", 1)
    api_ok = c.api_type in (ApiType.native_mqtt, ApiType.rest_http) and bool(c.own_broker)
    prog_ok = c.programmability in (Programmability.config_only, Programmability.rules_engine)
    outdoor = bool(c.outdoor) or (c.ip_rating or "").upper().startswith("IP6")
    return [
        ("LTE / 4G cellular (required)", bool(c.cellular), c.cellular_tech or "—"),
        ("MQTT/REST to own server (required)", api_ok, c.api_type.value),
        ("No firmware / config-only (required)", prog_ok, c.programmability.value),
        (
            "Relay output (required)",
            (c.lock.relay_count or 0) >= relay_min,
            f"{c.lock.relay_count} relay(s)" if c.lock.relay_count else "—",
        ),
        (
            "Reader interface (bonus)",
            _has_reader(c),
            "RS-485" if c.reader.rs485 else ("Wiegand/OSDP" if _has_reader(c) else "—"),
        ),
        ("WiFi (bonus)", c.wifi, "—"),
        ("Bluetooth (bonus)", c.bluetooth, "—"),
        (
            "CE + RED (bonus)",
            bool(c.cert.ce and c.cert.red),
            "CE+RED" if c.cert.ce and c.cert.red else "—",
        ),
        ("Outdoor IP65 (bonus)", outdoor, c.ip_rating or "—"),
    ]


def build_analysis_messages(c: Controller) -> list[ChatMessage]:
    system = (
        "You are a hardware sourcing analyst. The buyer runs their OWN access-control app "
        "(the brain); this device is a cellular connected relay it commands. Given the spec, "
        "return ONLY JSON with keys: scenarios (3-5 items {title, body} on how to MAXIMISE the "
        "device for door access), limitations (items {severity: high|medium, text}), mitigations "
        "(items {limitation, solution}), verdict (string). Be concrete and honest."
    )
    return [ChatMessage("system", system), ChatMessage("user", c.model_dump_json())]


def generate_analysis(c: Controller, *, ollama, model: str) -> dict:
    raw = ollama.chat(model, build_analysis_messages(c), temperature=0.4, json_mode=True)
    default = {"scenarios": [], "limitations": [], "mitigations": [], "verdict": ""}
    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return default
    if not isinstance(data, dict):
        return default
    return {k: data.get(k, default[k]) for k in _ANALYSIS_KEYS}


def _sev_icon(sev: str) -> str:
    return "🔴" if str(sev).lower().startswith("high") else "🟡"


def render_deep_dive(c: Controller, requirements: dict, analysis: dict) -> str:
    lines: list[str] = [f"# {c.vendor} {c.model} — deep dive", ""]

    warn = variant_warning(c)
    if warn:
        lines += [f"> ⚠️ **SKU trap:** {warn}", ""]

    lines += ["## Snapshot", ""]
    lines.append(f"- **SKU:** {c.sku or c.model}")
    lines.append(f"- **Origin:** {c.country_of_origin or 'unknown'}")
    price = f"€{c.price_eur}" if c.price_eur is not None else "unknown"
    lines.append(f"- **Indicative price:** {price}")
    if c.buy_links:
        lines.append("- **Buy:** " + ", ".join(c.buy_links))
    lines.append("")

    lines += ["## Criteria fit", "", "| Requirement | Met | Detail |", "|---|---|---|"]
    for label, met, detail in criteria_fit_rows(c, requirements):
        lines.append(f"| {label} | {'✅' if met else '❌'} | {detail} |")
    lines.append("")

    lines += ["## Real-world scenarios", ""]
    for i, s in enumerate(analysis.get("scenarios", []), 1):
        lines.append(f"### {i}. {s.get('title', '')}")
        lines.append(s.get("body", ""))
        lines.append("")

    lines += ["## Limitations", ""]
    for lim in analysis.get("limitations", []):
        lines.append(f"- {_sev_icon(lim.get('severity', ''))} {lim.get('text', '')}")
    lines.append("")

    lines += ["## Mitigations", ""]
    for m in analysis.get("mitigations", []):
        lines.append(f"- **{m.get('limitation', '')}** → {m.get('solution', '')}")
    lines.append("")

    lines += ["## Rebrand path & CE/RED", ""]
    lines.append(f"- **Rebrand path:** {c.rebrand_path.value}")
    lines.append(f"- **Certification:** CE={c.cert.ce} RED={c.cert.red}")
    lines.append("")

    lines += ["## Verdict", "", analysis.get("verdict", ""), ""]
    return "\n".join(lines)


def generate_deep_dive(c: Controller, requirements: dict, *, ollama, model: str) -> str:
    analysis = generate_analysis(c, ollama=ollama, model=model)
    return render_deep_dive(c, requirements, analysis)
