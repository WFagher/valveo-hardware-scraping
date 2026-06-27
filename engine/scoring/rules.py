"""Hard-criteria filter and weighted scoring for controllers."""
from __future__ import annotations

from ..models import Controller, Programmability, RebrandPath


def passes_hard_filters(c: Controller, requirements: dict) -> tuple[bool, list[str]]:
    hard = requirements.get("hard", {})
    reasons: list[str] = []
    if hard.get("cellular") == "required" and not c.cellular:
        reasons.append("no cellular")
    allowed_api = hard.get("api") or []
    if allowed_api and c.api_type.value not in allowed_api:
        reasons.append(f"api {c.api_type.value} not in {allowed_api}")
    allowed_prog = hard.get("programmability") or []
    if allowed_prog and c.programmability.value not in allowed_prog:
        reasons.append(f"programmability {c.programmability.value} not allowed")
    relay_min = hard.get("relay_min", 0)
    if (c.lock.relay_count or 0) < relay_min:
        reasons.append(f"relays {c.lock.relay_count} < {relay_min}")
    return (not reasons, reasons)


_REBRAND = {
    RebrandPath.oem_program: 1.0,
    RebrandPath.resell_as_is: 0.7,
    RebrandPath.recase_diy: 0.4,
    RebrandPath.none: 0.1,
}
_READY = {
    Programmability.config_only: 1.0,
    Programmability.rules_engine: 0.9,
    Programmability.sdk_required: 0.3,
    Programmability.unknown: 0.5,
}


def _spec_fit(c: Controller) -> float:
    has_reader = c.reader.wiegand or c.reader.osdp or c.reader.rs485 or c.reader.native_reader
    outdoor = bool(c.outdoor) or (c.ip_rating or "").upper().startswith("IP6")
    signals = [c.wifi, c.bluetooth, has_reader, bool(c.digital_inputs), outdoor]
    return sum(1 for s in signals if s) / len(signals)


def _ce_red(c: Controller) -> float:
    if c.cert.ce and c.cert.red:
        return 1.0
    return 0.6 if c.cert.ce else 0.0


def _commercial(c: Controller) -> float:
    if c.price_eur is None:
        return 0.5
    return max(0.0, min(1.0, 1 - (c.price_eur - 100) / 400))


def score_controller(c: Controller, weights: dict) -> float:
    return (
        weights["rebrandability"] * _REBRAND[c.rebrand_path]
        + weights["ready_to_install"] * _READY[c.programmability]
        + weights["spec_fit"] * _spec_fit(c)
        + weights["ce_red"] * _ce_red(c)
        + weights["commercial"] * _commercial(c)
    )
