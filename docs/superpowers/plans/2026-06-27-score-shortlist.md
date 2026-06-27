# Score + Segmented Shortlist Implementation Plan (Plan 3 of 5)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Apply the hard-criteria filter and a weighted score to stored `Controller` records, then produce a ranked shortlist sub-grouped by reader-capable vs relay-only — exposed via `engine matrix` and `engine shortlist`.

**Architecture:** Pure functions over `Controller` objects (no I/O), so they're trivially testable. `passes_hard_filters` returns `(ok, reasons)`. `score_controller` is a weighted sum of five 0–1 sub-scores keyed by `config/scoring_weights.yaml`. `build_shortlist` filters → scores → sorts; the CLI groups by segment for display.

**Tech Stack:** Python 3.12+ stdlib + pydantic models from Plan 1. No new dependencies.

## Global Constraints
- `from __future__ import annotations`; ruff line-length 100, py312.
- Reuse `engine.models` enums (`ApiType`, `Programmability`, `RebrandPath`) and `Controller`.
- Hard filter (spec §6): cellular required; `api_type ∈ {native_mqtt, rest_http}`; `programmability ∈ {config_only, rules_engine}`; `relay_count ≥ 1`. Unknown/missing values FAIL the hard filter (cannot confirm = excluded).
- Scoring weights come from `config/scoring_weights.yaml` and sum to 1.0.

## File Structure (this plan)
- `engine/scoring/__init__.py`, `engine/scoring/rules.py` — `passes_hard_filters`, `score_controller`, sub-score helpers.
- `engine/compare/__init__.py`, `engine/compare/shortlist.py` — `ScoredController`, `segment_of`, `tags_of`, `build_shortlist`.
- `engine/cli.py` — add `matrix`, `shortlist`.
- Tests: `tests/test_rules.py`, `tests/test_shortlist.py`, `tests/test_cli_shortlist.py`.

---

### Task 1: Hard filter + weighted score

**Files:**
- Create: `engine/scoring/__init__.py`, `engine/scoring/rules.py`
- Test: `tests/test_rules.py`

**Interfaces:**
- Produces:
  - `passes_hard_filters(c: Controller, requirements: dict) -> tuple[bool, list[str]]` — reads `requirements["hard"]`; returns `(True, [])` or `(False, reasons)`.
  - `score_controller(c: Controller, weights: dict) -> float` — weighted sum of five 0–1 sub-scores; result in `[0, 1]`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_rules.py
from __future__ import annotations
from engine.models import ApiType, Controller, Programmability, RebrandPath
from engine.scoring.rules import passes_hard_filters, score_controller

# NOTE: passes_hard_filters reads requirements["hard"], so pass the FULL requirements dict.
HARD = {"hard": {"cellular": "required", "api": ["native_mqtt", "rest_http"],
        "programmability": ["config_only", "rules_engine"], "relay_min": 1}}
WEIGHTS = {"rebrandability": 0.30, "ready_to_install": 0.20, "spec_fit": 0.25,
           "ce_red": 0.15, "commercial": 0.10}

def _good():
    c = Controller(vendor="Milesight", model="UC300-L05EU", cellular=True,
                   api_type=ApiType.native_mqtt, programmability=Programmability.rules_engine,
                   rebrand_path=RebrandPath.oem_program)
    c.lock.relay_count = 2
    c.cert.ce = True; c.cert.red = True
    return c

def test_good_controller_passes():
    ok, reasons = passes_hard_filters(_good(), HARD)
    assert ok is True and reasons == []

def test_no_cellular_fails():
    c = _good(); c.cellular = False
    ok, reasons = passes_hard_filters(c, HARD)
    assert ok is False and any("cellular" in r for r in reasons)

def test_vendor_cloud_only_fails():
    c = _good(); c.api_type = ApiType.vendor_cloud_only
    ok, reasons = passes_hard_filters(c, HARD)
    assert ok is False and any("api" in r for r in reasons)

def test_no_relay_fails():
    c = _good(); c.lock.relay_count = None
    ok, reasons = passes_hard_filters(c, HARD)
    assert ok is False and any("relay" in r for r in reasons)

def test_score_in_range_and_rewards_quality():
    bare = Controller(vendor="X", model="Y")
    assert 0.0 <= score_controller(bare, WEIGHTS) <= 1.0
    assert score_controller(_good(), WEIGHTS) > score_controller(bare, WEIGHTS)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_rules.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'engine.scoring'`

- [ ] **Step 3: Write the implementation**

```python
# engine/scoring/__init__.py
"""Scoring and filtering."""
from __future__ import annotations
```

```python
# engine/scoring/rules.py
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_rules.py -v`
Expected: PASS (5 passed)

- [ ] **Step 5: Commit**

```bash
git add engine/scoring tests/test_rules.py
git commit -m "feat: hard-criteria filter and weighted scoring"
```

---

### Task 2: Segmented shortlist builder

**Files:**
- Create: `engine/compare/__init__.py`, `engine/compare/shortlist.py`
- Test: `tests/test_shortlist.py`

**Interfaces:**
- Consumes: `passes_hard_filters`, `score_controller`.
- Produces:
  - `ScoredController` dataclass: `controller: Controller`, `score: float`, `segment: str`, `tags: list[str]`.
  - `segment_of(c) -> str` — `"reader-capable"` if any reader interface else `"relay-only"`.
  - `tags_of(c) -> list[str]` — subset of `["multi-door", "outdoor", "wifi", "ble", "oem"]`.
  - `build_shortlist(controllers, requirements, weights) -> list[ScoredController]` — filtered to passing, scored, sorted desc by score.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_shortlist.py
from __future__ import annotations
from engine.models import ApiType, Controller, Programmability, RebrandPath
from engine.compare.shortlist import build_shortlist, segment_of, tags_of

# NOTE: full requirements dict (build_shortlist forwards it to passes_hard_filters).
HARD = {"hard": {"cellular": "required", "api": ["native_mqtt", "rest_http"],
        "programmability": ["config_only", "rules_engine"], "relay_min": 1}}
WEIGHTS = {"rebrandability": 0.30, "ready_to_install": 0.20, "spec_fit": 0.25,
           "ce_red": 0.15, "commercial": 0.10}

def _passing(vendor, *, oem=RebrandPath.none, rs485=False):
    c = Controller(vendor=vendor, model="M", cellular=True, api_type=ApiType.native_mqtt,
                   programmability=Programmability.rules_engine, rebrand_path=oem)
    c.lock.relay_count = 2
    c.reader.rs485 = rs485
    return c

def test_segment_and_tags():
    reader = _passing("A", rs485=True)
    assert segment_of(reader) == "reader-capable"
    assert segment_of(_passing("B")) == "relay-only"
    reader.lock.relay_count = 4
    assert "multi-door" in tags_of(reader)

def test_build_shortlist_filters_and_ranks():
    high = _passing("High", oem=RebrandPath.oem_program, rs485=True)
    low = _passing("Low", oem=RebrandPath.none)
    failing = Controller(vendor="Fail", model="Z", cellular=False)
    ranked = build_shortlist([low, failing, high], HARD, WEIGHTS)
    assert [s.controller.vendor for s in ranked] == ["High", "Low"]  # Fail excluded, sorted desc
    assert ranked[0].score >= ranked[1].score
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_shortlist.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'engine.compare'`

- [ ] **Step 3: Write the implementation**

```python
# engine/compare/__init__.py
"""Comparison / shortlist."""
from __future__ import annotations
```

```python
# engine/compare/shortlist.py
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_shortlist.py -v`
Expected: PASS (2 passed)

- [ ] **Step 5: Commit**

```bash
git add engine/compare tests/test_shortlist.py
git commit -m "feat: segmented shortlist builder"
```

---

### Task 3: CLI — matrix, shortlist

**Files:**
- Modify: `engine/cli.py`
- Test: `tests/test_cli_shortlist.py`

**Interfaces:**
- Consumes: `build_shortlist`, `load_scoring`, `DeviceStore`.
- Produces: `matrix` (table of every stored controller); `shortlist --top N` (ranked, grouped by segment).

- [ ] **Step 1: Write the failing test**

```python
# tests/test_cli_shortlist.py
from __future__ import annotations
from click.testing import CliRunner
import engine.cli as cli
from engine.config import Config
from engine.models import ApiType, Controller, Programmability, RebrandPath
from engine.store import DeviceStore

def _seed(tmp_path):
    store = DeviceStore(Config.load().db_path())
    try:
        good = Controller(vendor="Milesight", model="UC300-L05EU", cellular=True,
                          api_type=ApiType.native_mqtt,
                          programmability=Programmability.rules_engine,
                          rebrand_path=RebrandPath.oem_program)
        good.lock.relay_count = 2
        store.upsert(good)
        store.upsert(Controller(vendor="FailCo", model="NoCell", cellular=False))
    finally:
        store.close()

def test_shortlist_shows_passing_only(monkeypatch, tmp_path):
    monkeypatch.setenv("ENGINE_DATA_DIR", str(tmp_path / "data"))
    _seed(tmp_path)
    result = CliRunner().invoke(cli.main, ["shortlist"])
    assert result.exit_code == 0
    assert "Milesight" in result.output
    assert "FailCo" not in result.output

def test_matrix_lists_all(monkeypatch, tmp_path):
    monkeypatch.setenv("ENGINE_DATA_DIR", str(tmp_path / "data"))
    _seed(tmp_path)
    result = CliRunner().invoke(cli.main, ["matrix"])
    assert result.exit_code == 0
    assert "Milesight" in result.output and "FailCo" in result.output
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_cli_shortlist.py -v`
Expected: FAIL — `Error: No such command 'shortlist'`

- [ ] **Step 3: Extend `engine/cli.py`** — add imports and two commands:

```python
# add to imports in engine/cli.py
from .compare.shortlist import build_shortlist
from .research_config import load_requirements, load_scoring
```
(Note: `load_requirements` is already imported — change that line to import both.)

```python
# add these commands before `if __name__ == "__main__":`
@main.command()
def matrix() -> None:
    """Print a spec matrix of every stored controller."""
    cfg = Config.load()
    store = DeviceStore(cfg.db_path())
    try:
        controllers = store.all()
    finally:
        store.close()
    table = Table()
    for col in ("Vendor", "Model", "Cellular", "API", "Relays", "WiFi", "BLE"):
        table.add_column(col)
    for c in controllers:
        table.add_row(c.vendor, c.model, str(c.cellular), c.api_type.value,
                      str(c.lock.relay_count), str(c.wifi), str(c.bluetooth))
    console.print(table)


@main.command()
@click.option("--top", default=10, help="Max items per segment.")
def shortlist(top: int) -> None:
    """Ranked shortlist, grouped by reader-capable vs relay-only."""
    cfg = Config.load()
    req = load_requirements(cfg.config_dir)
    weights = load_scoring(cfg.config_dir)["weights"]
    store = DeviceStore(cfg.db_path())
    try:
        controllers = store.all()
    finally:
        store.close()
    ranked = build_shortlist(controllers, req, weights)
    if not ranked:
        console.print("[yellow]No controllers pass the hard criteria yet.[/yellow]")
        return
    for seg in ("reader-capable", "relay-only"):
        items = [s for s in ranked if s.segment == seg][:top]
        if not items:
            continue
        console.print(f"[bold]{seg}[/bold]")
        for i, s in enumerate(items, 1):
            tags = " ".join(s.tags)
            console.print(
                f"  {i}. {s.controller.vendor} {s.controller.model} "
                f"— {s.score * 10:.1f}/10  {tags}"
            )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_cli_shortlist.py -v`
Expected: PASS (2 passed)

- [ ] **Step 5: Full suite + lint**

Run: `uv run pytest -q && uv run ruff check engine tests`
Expected: all pass; ruff clean.

- [ ] **Step 6: Commit**

```bash
git add engine/cli.py tests/test_cli_shortlist.py
git commit -m "feat: matrix and shortlist CLI commands"
```

---

## Done criteria for Plan 3
- `uv run pytest -q` green.
- `engine matrix` lists all stored controllers; `engine shortlist` ranks the passing ones, grouped by segment.

Then proceed to **Plan 4 — Per-device deep-dive report** (the signature output, spec §2.1).
