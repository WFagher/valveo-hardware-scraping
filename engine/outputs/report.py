"""Write the live ranked shortlist to reports/shortlist-latest.md."""
from __future__ import annotations

from pathlib import Path

from ..compare.shortlist import build_shortlist
from ..config import Config
from ..research_config import load_requirements, load_scoring
from ..store import DeviceStore


def _fmt(value: object) -> str:
    if value is None:
        return "?"
    return str(value)


def render_report(controllers, requirements, weights, *, total, seen, timestamp="") -> str:
    ranked = build_shortlist(controllers, requirements, weights)
    lines = ["# Live shortlist — cellular connected-relay door controllers", ""]
    if timestamp:
        lines.append(f"_Updated: {timestamp}_")
    lines.append(
        f"_Devices evaluated: {total} · pages crawled: {seen} · "
        f"passing hard filter: {len(ranked)}_"
    )
    lines.append("")
    if not ranked:
        lines += ["_No devices pass the hard criteria yet._", ""]
    for seg in ("reader-capable", "relay-only"):
        items = [s for s in ranked if s.segment == seg]
        if not items:
            continue
        lines += [
            f"## {seg}",
            "",
            "| # | Device | Score | Origin | OEM | Relays | API | Tags |",
            "|---|---|---|---|---|---|---|---|",
        ]
        for i, s in enumerate(items, 1):
            c = s.controller
            lines.append(
                f"| {i} | {c.vendor} {c.model} | {s.score * 10:.1f} | "
                f"{_fmt(c.country_of_origin)} | {_fmt(c.oem.offered)} | "
                f"{_fmt(c.lock.relay_count)} | {c.api_type.value} | {' '.join(s.tags)} |"
            )
        lines.append("")
    return "\n".join(lines)


def write_shortlist_report(cfg: Config, *, timestamp: str = "") -> Path:
    req = load_requirements(cfg.config_dir)
    weights = load_scoring(cfg.config_dir)["weights"]
    store = DeviceStore(cfg.db_path())
    try:
        controllers = store.all()
        total = store.count()
        seen = store.seen_count()
    finally:
        store.close()
    md = render_report(controllers, req, weights, total=total, seen=seen, timestamp=timestamp)
    out = cfg.data_dir.parent / "reports" / "shortlist-latest.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(md)
    return out
