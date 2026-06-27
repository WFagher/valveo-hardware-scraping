# Scheduler / Always-On Implementation Plan (Plan 5 of 5)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an always-on daemon that re-crawls the seed sources on a schedule, and DRY the discovery loop into a shared `pipeline.run_discovery_cycle` used by both `engine discover` and the scheduler.

**Architecture:** `pipeline.run_discovery_cycle(cfg)` owns the fetch→extract→upsert loop (with an optional `on_result` callback for CLI progress). `scheduler.build_scheduler(cfg)` registers a daily APScheduler cron job calling it; `engine scheduler` starts the blocking daemon. APScheduler is imported lazily inside the CLI command so other commands and tests stay light.

**Tech Stack:** Python 3.12+, apscheduler (new dep), existing modules. 

## Global Constraints
- `from __future__ import annotations`; ruff line-length 100, py312.
- DRY: the discovery loop lives in ONE place (`engine/pipeline.py`); `cli.discover` and the scheduler both call it.
- Tests never start the blocking scheduler and never hit the network/model (monkeypatch module-level `fetch_text`, `extract_controller`, `OllamaClient`).

## File Structure (this plan)
- `pyproject.toml` — add `apscheduler>=3.10`.
- `engine/pipeline.py` — `run_discovery_cycle`.
- `engine/scheduler.py` — `build_scheduler`, `start`.
- `engine/cli.py` — refactor `discover` to use the pipeline; add `scheduler` command.
- Tests: `tests/test_pipeline.py`, `tests/test_scheduler.py`.

---

### Task 1: Shared discovery pipeline

**Files:**
- Create: `engine/pipeline.py`
- Modify: `engine/cli.py` (refactor `discover`)
- Test: `tests/test_pipeline.py`

**Interfaces:**
- Produces: `run_discovery_cycle(cfg: Config, *, on_result=None) -> tuple[int, int]` — returns `(stored, total)`. `on_result(url, controller_or_none)` is called per URL if provided. Module-level names `fetch_text`, `extract_controller`, `OllamaClient`, `_seed_urls` are monkeypatch points.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_pipeline.py
from __future__ import annotations
import engine.pipeline as pipeline
from engine.config import Config
from engine.models import Controller
from engine.store import DeviceStore

class _DummyOllama:
    def __init__(self, *a, **k): pass
    def __enter__(self): return self
    def __exit__(self, *e): pass

def test_run_discovery_cycle_stores_only_valid(monkeypatch, tmp_path):
    monkeypatch.setenv("ENGINE_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setattr(pipeline, "OllamaClient", _DummyOllama)
    monkeypatch.setattr(pipeline, "_seed_urls", lambda cfg: ["u1", "u2"])
    monkeypatch.setattr(pipeline, "fetch_text", lambda url, **k: "text " + url)
    monkeypatch.setattr(
        pipeline, "extract_controller",
        lambda text, **kw: Controller(vendor="V", model="M")
        if "u1" in (kw.get("source_url") or "") else None,
    )
    stored, total = pipeline.run_discovery_cycle(Config.load())
    assert (stored, total) == (1, 2)
    store = DeviceStore(Config.load().db_path())
    try:
        assert store.count() == 1
    finally:
        store.close()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_pipeline.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'engine.pipeline'`

- [ ] **Step 3: Write the pipeline**

```python
# engine/pipeline.py
"""Discovery cycle shared by the CLI and the scheduler."""
from __future__ import annotations

from collections.abc import Callable

import yaml

from .config import Config
from .crawlers.fetcher import fetch_text
from .extractors.spec_extractor import extract_controller
from .llm.ollama_client import OllamaClient
from .models import Controller
from .store import DeviceStore


def _seed_urls(cfg: Config) -> list[str]:
    data = yaml.safe_load((cfg.config_dir / "seed_urls.yaml").read_text())
    return data.get("urls", [])


def run_discovery_cycle(
    cfg: Config, *, on_result: Callable[[str, Controller | None], None] | None = None
) -> tuple[int, int]:
    urls = _seed_urls(cfg)
    store = DeviceStore(cfg.db_path())
    stored = 0
    try:
        with OllamaClient(cfg.ollama_host) as ol:
            for url in urls:
                text = fetch_text(url)
                controller = extract_controller(
                    text, ollama=ol, model=cfg.chat_model, source_url=url
                )
                if controller is not None:
                    store.upsert(controller)
                    stored += 1
                if on_result is not None:
                    on_result(url, controller)
    finally:
        store.close()
    return stored, len(urls)
```

- [ ] **Step 4: Refactor `engine/cli.py` `discover`** — replace the existing `discover` command body with a call to the pipeline. Add `from .pipeline import run_discovery_cycle` to imports and replace the whole `discover` function with:

```python
@main.command()
def discover() -> None:
    """Extract controllers from every URL in config/seed_urls.yaml."""
    cfg = Config.load()

    def _print(url: str, controller) -> None:
        if controller is not None:
            console.print(f"  [green]+[/green] {controller.vendor} {controller.model}")
        else:
            console.print(f"  [yellow]-[/yellow] {url}")

    stored, total = run_discovery_cycle(cfg, on_result=_print)
    console.print(f"Discovered {stored}/{total} controllers.")
```

- [ ] **Step 5: Run tests + full suite**

Run: `uv run pytest tests/test_pipeline.py tests/test_cli_extract.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add engine/pipeline.py engine/cli.py tests/test_pipeline.py
git commit -m "refactor: shared run_discovery_cycle pipeline used by discover"
```

---

### Task 2: Scheduler daemon

**Files:**
- Modify: `pyproject.toml` (add apscheduler), `engine/cli.py` (add `scheduler` command)
- Create: `engine/scheduler.py`
- Test: `tests/test_scheduler.py`

**Interfaces:**
- Produces: `build_scheduler(cfg: Config) -> BlockingScheduler` (registers a `daily-discovery` cron job at 04:00 Europe/Stockholm); `start() -> None`. CLI `scheduler` command starts it.

- [ ] **Step 1: Add the dependency**

Edit `pyproject.toml` dependencies list — add `"apscheduler>=3.10",`. Then run `uv sync`.

- [ ] **Step 2: Write the failing test**

```python
# tests/test_scheduler.py
from __future__ import annotations
from engine.config import Config
from engine.scheduler import build_scheduler

def test_build_scheduler_registers_discovery_job(monkeypatch, tmp_path):
    monkeypatch.setenv("ENGINE_DATA_DIR", str(tmp_path / "data"))
    sched = build_scheduler(Config.load())
    job_ids = {j.id for j in sched.get_jobs()}
    assert "daily-discovery" in job_ids
```

- [ ] **Step 3: Run test to verify it fails**

Run: `uv run pytest tests/test_scheduler.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'engine.scheduler'`

- [ ] **Step 4: Write the scheduler**

```python
# engine/scheduler.py
"""APScheduler daemon: periodic discovery re-crawl."""
from __future__ import annotations

from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger
from rich.console import Console

from .config import Config
from .pipeline import run_discovery_cycle

console = Console()


def _discovery_job(cfg: Config) -> None:
    stored, total = run_discovery_cycle(cfg)
    console.print(f"[discovery] stored {stored}/{total}")


def build_scheduler(cfg: Config) -> BlockingScheduler:
    sched = BlockingScheduler(timezone="Europe/Stockholm")
    sched.add_job(
        _discovery_job,
        CronTrigger(hour=4, minute=0),
        args=[cfg],
        id="daily-discovery",
        name="Daily discovery re-crawl",
    )
    return sched


def start() -> None:
    cfg = Config.load()
    sched = build_scheduler(cfg)
    console.print(
        "[bold]engine scheduler[/bold] — daily discovery 04:00 Europe/Stockholm. Ctrl+C to stop."
    )
    try:
        sched.start()
    except (KeyboardInterrupt, SystemExit):
        console.print("stopped.")
```

- [ ] **Step 5: Add the `scheduler` CLI command** — append to `engine/cli.py` before `if __name__`:

```python
@main.command()
def scheduler() -> None:
    """Start the always-on scheduler (daily discovery re-crawl)."""
    from .scheduler import start

    start()
```

- [ ] **Step 6: Run tests + full suite + lint**

Run: `uv run pytest -q && uv run ruff check engine tests`
Expected: all pass; ruff clean.

- [ ] **Step 7: Commit**

```bash
git add pyproject.toml uv.lock engine/scheduler.py engine/cli.py tests/test_scheduler.py
git commit -m "feat: APScheduler daemon with daily discovery re-crawl"
```

---

## Done criteria for Plan 5
- `uv run pytest -q` green.
- `engine scheduler` starts a blocking daemon that re-runs discovery daily.
- The discovery loop exists in exactly one place (`pipeline.run_discovery_cycle`).

**The engine is now feature-complete:** discover → extract → store → score → shortlist → deep-dive, with an always-on scheduler.
