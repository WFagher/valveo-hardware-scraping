"""Build a ranked, segmented shortlist from scored controllers."""
from __future__ import annotations

from dataclasses import dataclass, field

from ..models import Controller, RebrandPath
from ..scoring.rules import passes_hard_filters, score_controller


@dataclass
class ScoredController:
    controller: Controller
    score: float
    segment: str
    tags: list[str] = field(default_factory=list)


def segment_of(c: Controller) -> str:
    if c.reader.wiegand or c.reader.osdp or c.reader.rs485 or c.reader.native_reader:
        return "reader-capable"
    return "relay-only"


def tags_of(c: Controller) -> list[str]:
    tags: list[str] = []
    if (c.lock.relay_count or 0) >= 4:
        tags.append("multi-door")
    if bool(c.outdoor) or (c.ip_rating or "").upper().startswith("IP6"):
        tags.append("outdoor")
    if c.wifi:
        tags.append("wifi")
    if c.bluetooth:
        tags.append("ble")
    if c.rebrand_path is RebrandPath.oem_program:
        tags.append("oem")
    return tags


def build_shortlist(
    controllers: list[Controller], requirements: dict, weights: dict
) -> list[ScoredController]:
    scored: list[ScoredController] = []
    for c in controllers:
        ok, _ = passes_hard_filters(c, requirements)
        if not ok:
            continue
        scored.append(
            ScoredController(c, score_controller(c, weights), segment_of(c), tags_of(c))
        )
    scored.sort(key=lambda s: s.score, reverse=True)
    return scored
