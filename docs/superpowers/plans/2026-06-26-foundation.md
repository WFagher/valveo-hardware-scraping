# Foundation Implementation Plan (Plan 1 of 5)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stand up the `door-hardware-sourcing-engine` skeleton — project scaffold, the `Controller` data model, a SQLite device store, config loading, seed config files, and a thin `engine` CLI — so later plans can crawl, score, and report against a working core.

**Architecture:** A lean clone of `arena-research-engine`. Single Python package `engine/` exposed via a `click` CLI. Devices are pydantic models persisted as JSON rows in SQLite, deduped by `(vendor, model)`. Config (Ollama endpoints, paths) comes from `.env`; research rules (hard criteria, sources, scoring) come from YAML in `config/`.

**Tech Stack:** Python 3.12+, uv, pydantic v2, click, rich, pyyaml, python-dotenv, pytest, ruff. SQLite via stdlib `sqlite3`.

## Global Constraints

- Python `>=3.12`; `from __future__ import annotations` at the top of every module.
- Package name `engine`; CLI entry point `engine = "engine.cli:main"`.
- ruff line-length 100, target `py312`.
- Reference benchmark device is **Milesight UC300-L05EU** (cellular `-L0xx`, NOT LoRaWAN `-868M`).
- Hard criteria (from spec §6): cellular required; API ∈ {native_mqtt, rest_http} to own broker (vendor-cloud-only excluded); programmability ∈ {config_only, rules_engine}; ≥1 relay.
- All persisted models serialize via pydantic `model_dump_json()` / `model_validate_json()`.
- Tests use `pytest`; SQLite tests use `tmp_path` fixtures (never touch `./data`).

## Subsequent plans (not in this plan)
- Plan 2 — Crawl + LLM extract (vendor/distributor/datasheet → `Controller` records + verification).
- Plan 3 — Score + compare + segmented shortlist.
- Plan 4 — Per-device deep-dive report generator (spec §2.1).
- Plan 5 — Scheduler / always-on re-crawl.

## File Structure (this plan)
- `pyproject.toml` — project metadata, deps, entry point, ruff.
- `.env.example` — env template.
- `engine/__init__.py` — version.
- `engine/models.py` — enums + `Controller`, `ReaderSupport`, `LockSupport`, `OEMProgram`, `Certification`.
- `engine/store.py` — `DeviceStore` (SQLite upsert/get/all/count, dedup by key).
- `engine/config.py` — `Config` dataclass loaded from env.
- `engine/research_config.py` — load/validate the YAML rule files.
- `engine/cli.py` — `click` group: `paths`, `db-info`, `requirements`.
- `config/requirements.yaml`, `config/sources.yaml`, `config/spec_schema.yaml`, `config/scoring_weights.yaml`.
- `tests/test_models.py`, `tests/test_store.py`, `tests/test_config.py`, `tests/test_research_config.py`, `tests/test_cli.py`.

---

### Task 1: Project scaffold

**Files:**
- Create: `pyproject.toml`, `engine/__init__.py`, `.env.example`, `tests/__init__.py`
- Test: `tests/test_smoke.py`

**Interfaces:**
- Produces: importable `engine` package exposing `engine.__version__: str`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_smoke.py
from __future__ import annotations
import engine

def test_version_present():
    assert isinstance(engine.__version__, str)
    assert engine.__version__
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_smoke.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'engine'`

- [ ] **Step 3: Create `pyproject.toml`**

```toml
[project]
name = "door-hardware-sourcing-engine"
version = "0.1.0"
description = "Local-LLM research engine for sourcing re-brandable cellular connected-relay door controllers"
requires-python = ">=3.12"
dependencies = [
    "httpx>=0.28",
    "pydantic>=2.10",
    "click>=8.1",
    "rich>=13.9",
    "pyyaml>=6.0",
    "python-dotenv>=1.0",
]

[dependency-groups]
dev = ["pytest>=8.0", "ruff>=0.6"]

[project.scripts]
engine = "engine.cli:main"

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["engine"]

[tool.ruff]
line-length = 100
target-version = "py312"
```

- [ ] **Step 4: Create package + env template**

```python
# engine/__init__.py
"""door-hardware-sourcing-engine."""
from __future__ import annotations

__version__ = "0.1.0"
```

```python
# tests/__init__.py
```

```dotenv
# .env.example
OLLAMA_HOST=http://localhost:11434
OLLAMA_CHAT_MODEL=llama3.3:70b-instruct-q3_K_M
OLLAMA_FAST_MODEL=llama3.2:3b
OLLAMA_EMBED_MODEL=nomic-embed-text
ENGINE_DATA_DIR=./data
ENGINE_CONFIG_DIR=./config
```

- [ ] **Step 5: Sync and run the test**

Run: `uv sync && uv run pytest tests/test_smoke.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add pyproject.toml engine/__init__.py tests/__init__.py tests/test_smoke.py .env.example uv.lock
git commit -m "feat: project scaffold for door-hardware-sourcing-engine"
```

---

### Task 2: Core data model

**Files:**
- Create: `engine/models.py`
- Test: `tests/test_models.py`

**Interfaces:**
- Produces:
  - Enums: `Category` (`controller`), `RebrandPath` (`oem_program|recase_diy|resell_as_is|none`), `ApiType` (`native_mqtt|rest_http|vendor_cloud_only|unknown`), `Programmability` (`config_only|rules_engine|sdk_required|unknown`).
  - Models: `ReaderSupport`, `LockSupport`, `OEMProgram`, `Certification`, `Controller`.
  - `Controller.key -> str` = `f"{vendor.strip().lower()}::{model.strip().lower()}"`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_models.py
from __future__ import annotations
from engine.models import Controller, ApiType, Programmability, RebrandPath

def test_controller_defaults_and_key():
    c = Controller(vendor="Milesight", model="UC300-L05EU")
    assert c.key == "milesight::uc300-l05eu"
    assert c.api_type is ApiType.unknown
    assert c.programmability is Programmability.unknown
    assert c.rebrand_path is RebrandPath.none
    assert c.wifi is False and c.bluetooth is False
    assert c.reader.rs485 is False
    assert c.buy_links == []

def test_controller_json_roundtrip():
    c = Controller(
        vendor="Milesight", model="UC300-L05EU", sku="UC300-L05EU",
        cellular=True, cellular_tech="LTE Cat 1",
        api_type=ApiType.native_mqtt, programmability=Programmability.rules_engine,
        own_broker=True, digital_inputs=4,
    )
    c.lock.relay_count = 2
    raw = c.model_dump_json()
    back = Controller.model_validate_json(raw)
    assert back == c
    assert back.lock.relay_count == 2
    assert back.api_type is ApiType.native_mqtt
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_models.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'engine.models'`

- [ ] **Step 3: Write the implementation**

```python
# engine/models.py
"""Pydantic data model for a door-access controller (the only searched category)."""
from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field


class Category(str, Enum):
    controller = "controller"


class RebrandPath(str, Enum):
    oem_program = "oem_program"
    recase_diy = "recase_diy"
    resell_as_is = "resell_as_is"
    none = "none"


class ApiType(str, Enum):
    native_mqtt = "native_mqtt"
    rest_http = "rest_http"
    vendor_cloud_only = "vendor_cloud_only"
    unknown = "unknown"


class Programmability(str, Enum):
    config_only = "config_only"
    rules_engine = "rules_engine"
    sdk_required = "sdk_required"
    unknown = "unknown"


class ReaderSupport(BaseModel):
    wiegand: bool = False
    osdp: bool = False
    rs485: bool = False
    rs232: bool = False
    native_reader: bool = False
    notes: str | None = None


class LockSupport(BaseModel):
    relay_count: int | None = None
    relay_rating: str | None = None
    dry_contact: bool | None = None
    notes: str | None = None


class OEMProgram(BaseModel):
    offered: bool | None = None
    logo_on_device: bool | None = None
    custom_firmware: bool | None = None
    moq: int | None = None
    holds_ce: str | None = None  # "vendor" | "buyer" | None
    notes: str | None = None


class Certification(BaseModel):
    ce: bool | None = None
    red: bool | None = None
    en60839: bool | None = None
    rohs: bool | None = None
    doc_available: bool | None = None
    notes: str | None = None


class Controller(BaseModel):
    vendor: str
    model: str
    sku: str | None = None
    category: Category = Category.controller
    country_of_origin: str | None = None

    # connectivity
    cellular: bool | None = None
    cellular_tech: str | None = None
    wifi: bool = False
    bluetooth: bool = False
    ethernet: bool = False

    # control
    api_type: ApiType = ApiType.unknown
    protocols: list[str] = Field(default_factory=list)
    programmability: Programmability = Programmability.unknown
    own_broker: bool | None = None

    # I/O
    reader: ReaderSupport = Field(default_factory=ReaderSupport)
    lock: LockSupport = Field(default_factory=LockSupport)
    digital_inputs: int | None = None

    # physical
    ip_rating: str | None = None
    outdoor: bool | None = None
    power: str | None = None
    backup_battery: bool | None = None

    # commercial
    price_eur: float | None = None
    moq: int | None = None
    buy_links: list[str] = Field(default_factory=list)

    # rebrand / certification
    rebrand_path: RebrandPath = RebrandPath.none
    oem: OEMProgram = Field(default_factory=OEMProgram)
    cert: Certification = Field(default_factory=Certification)

    # provenance
    sources: list[str] = Field(default_factory=list)
    notes: str | None = None

    @property
    def key(self) -> str:
        return f"{self.vendor.strip().lower()}::{self.model.strip().lower()}"
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_models.py -v`
Expected: PASS (2 passed)

- [ ] **Step 5: Commit**

```bash
git add engine/models.py tests/test_models.py
git commit -m "feat: Controller data model with reader/lock/OEM/cert blocks"
```

---

### Task 3: SQLite device store

**Files:**
- Create: `engine/store.py`
- Test: `tests/test_store.py`

**Interfaces:**
- Consumes: `engine.models.Controller`.
- Produces: `DeviceStore(db_path: Path)` with `upsert(c: Controller) -> None`, `get(key: str) -> Controller | None`, `all() -> list[Controller]`, `count() -> int`, `close() -> None`. Dedup is by `Controller.key` (upsert replaces).

- [ ] **Step 1: Write the failing test**

```python
# tests/test_store.py
from __future__ import annotations
from engine.models import Controller, ApiType
from engine.store import DeviceStore

def test_upsert_get_count_dedup(tmp_path):
    store = DeviceStore(tmp_path / "devices.sqlite3")
    try:
        store.upsert(Controller(vendor="Milesight", model="UC300-L05EU", cellular=True))
        assert store.count() == 1
        got = store.get("milesight::uc300-l05eu")
        assert got is not None and got.cellular is True

        # upsert same key updates, does not duplicate
        store.upsert(Controller(vendor="Milesight", model="UC300-L05EU",
                                cellular=True, api_type=ApiType.native_mqtt))
        assert store.count() == 1
        assert store.get("milesight::uc300-l05eu").api_type is ApiType.native_mqtt

        store.upsert(Controller(vendor="Teracom", model="TCG120-4"))
        assert store.count() == 2
        assert {c.vendor for c in store.all()} == {"Milesight", "Teracom"}
    finally:
        store.close()

def test_get_missing_returns_none(tmp_path):
    store = DeviceStore(tmp_path / "devices.sqlite3")
    try:
        assert store.get("nope::nope") is None
    finally:
        store.close()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_store.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'engine.store'`

- [ ] **Step 3: Write the implementation**

```python
# engine/store.py
"""SQLite persistence for Controller records, deduped by (vendor, model)."""
from __future__ import annotations

import sqlite3
from pathlib import Path

from .models import Controller


class DeviceStore:
    def __init__(self, db_path: Path) -> None:
        self.conn = sqlite3.connect(db_path)
        self.conn.execute(
            "CREATE TABLE IF NOT EXISTS controllers ("
            "key TEXT PRIMARY KEY, vendor TEXT, model TEXT, data TEXT)"
        )
        self.conn.commit()

    def upsert(self, c: Controller) -> None:
        self.conn.execute(
            "INSERT INTO controllers(key, vendor, model, data) VALUES(?,?,?,?) "
            "ON CONFLICT(key) DO UPDATE SET vendor=excluded.vendor, "
            "model=excluded.model, data=excluded.data",
            (c.key, c.vendor, c.model, c.model_dump_json()),
        )
        self.conn.commit()

    def get(self, key: str) -> Controller | None:
        row = self.conn.execute(
            "SELECT data FROM controllers WHERE key=?", (key,)
        ).fetchone()
        return Controller.model_validate_json(row[0]) if row else None

    def all(self) -> list[Controller]:
        rows = self.conn.execute("SELECT data FROM controllers").fetchall()
        return [Controller.model_validate_json(r[0]) for r in rows]

    def count(self) -> int:
        return self.conn.execute("SELECT COUNT(*) FROM controllers").fetchone()[0]

    def close(self) -> None:
        self.conn.close()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_store.py -v`
Expected: PASS (2 passed)

- [ ] **Step 5: Commit**

```bash
git add engine/store.py tests/test_store.py
git commit -m "feat: SQLite DeviceStore with upsert/get/all/count dedup"
```

---

### Task 4: Config loader

**Files:**
- Create: `engine/config.py`
- Test: `tests/test_config.py`

**Interfaces:**
- Produces: frozen `Config` with fields `ollama_host, chat_model, fast_model, embed_model, data_dir: Path, config_dir: Path`; classmethod `load() -> Config` (reads env with the defaults from `.env.example`); method `db_path() -> Path` (ensures `data_dir` exists, returns `data_dir / "devices.sqlite3"`).

- [ ] **Step 1: Write the failing test**

```python
# tests/test_config.py
from __future__ import annotations
from pathlib import Path
from engine.config import Config

def test_load_defaults(monkeypatch, tmp_path):
    for var in ("OLLAMA_HOST", "OLLAMA_CHAT_MODEL", "ENGINE_DATA_DIR", "ENGINE_CONFIG_DIR"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("ENGINE_DATA_DIR", str(tmp_path / "data"))
    cfg = Config.load()
    assert cfg.ollama_host == "http://localhost:11434"
    assert cfg.chat_model.startswith("llama3.3")
    assert cfg.db_path() == (tmp_path / "data" / "devices.sqlite3").resolve()
    assert cfg.db_path().parent.is_dir()  # db_path() creates data_dir
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_config.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'engine.config'`

- [ ] **Step 3: Write the implementation**

```python
# engine/config.py
"""Runtime config loaded from .env / process environment."""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()


@dataclass(frozen=True)
class Config:
    ollama_host: str
    chat_model: str
    fast_model: str
    embed_model: str
    data_dir: Path
    config_dir: Path

    @classmethod
    def load(cls) -> "Config":
        return cls(
            ollama_host=os.environ.get("OLLAMA_HOST", "http://localhost:11434"),
            chat_model=os.environ.get("OLLAMA_CHAT_MODEL", "llama3.3:70b-instruct-q3_K_M"),
            fast_model=os.environ.get("OLLAMA_FAST_MODEL", "llama3.2:3b"),
            embed_model=os.environ.get("OLLAMA_EMBED_MODEL", "nomic-embed-text"),
            data_dir=Path(os.environ.get("ENGINE_DATA_DIR", "./data")).resolve(),
            config_dir=Path(os.environ.get("ENGINE_CONFIG_DIR", "./config")).resolve(),
        )

    def db_path(self) -> Path:
        self.data_dir.mkdir(parents=True, exist_ok=True)
        return self.data_dir / "devices.sqlite3"
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_config.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add engine/config.py tests/test_config.py
git commit -m "feat: Config loader from .env with db_path helper"
```

---

### Task 5: Seed config YAMLs + research-config loader

**Files:**
- Create: `config/requirements.yaml`, `config/sources.yaml`, `config/scoring_weights.yaml`, `config/spec_schema.yaml`, `engine/research_config.py`
- Test: `tests/test_research_config.py`

**Interfaces:**
- Consumes: `Config.config_dir`.
- Produces: `load_requirements(config_dir: Path) -> dict`, `load_sources(config_dir: Path) -> dict`, `load_scoring(config_dir: Path) -> dict`. Each reads the matching YAML and returns the parsed dict; raises `FileNotFoundError` if absent.

- [ ] **Step 1: Create the seed YAML files**

```yaml
# config/requirements.yaml
# Hard criteria are filters; bonus items boost score only. Decided 2026-06-26.
hard:
  cellular: required          # LTE/4G; LoRaWAN / NB-IoT-only is EXCLUDED
  api: [native_mqtt, rest_http]   # to the user's OWN broker; vendor_cloud_only EXCLUDED
  programmability: [config_only, rules_engine]   # no firmware coding
  relay_min: 1
bonus:
  wifi: backup_wan            # low priority
  bluetooth: phone_key_via_reader   # met at reader layer, not controller
  reader_interface: [wiegand, osdp, rs485]
  door_io: [door_contact, rex, tamper]
  oem_program: true
  ce_red: true
  ip65: true
benchmark: "Milesight UC300-L05EU"
```

```yaml
# config/sources.yaml
tiers:
  cellular_iot_controllers:
    - Milesight
    - King Pigeon
    - Teracom
    - ControlByWeb
    - Robustel
    - BLIIoT
    - Teltonika
  nordic_eu_incumbents:
    - Aptus
    - RCO
    - Axema
  marketplaces:
    - alibaba.com
    - made-in-china.com
```

```yaml
# config/scoring_weights.yaml
weights:
  rebrandability: 0.30
  ready_to_install: 0.20
  spec_fit: 0.25
  ce_red: 0.15
  commercial: 0.10
```

```yaml
# config/spec_schema.yaml
# Informational mirror of engine/models.py::Controller (the real schema).
fields:
  - vendor
  - model
  - sku
  - cellular
  - api_type
  - programmability
  - lock.relay_count
  - reader
  - cert
  - oem
```

- [ ] **Step 2: Write the failing test**

```python
# tests/test_research_config.py
from __future__ import annotations
from pathlib import Path
import pytest
from engine.research_config import load_requirements, load_sources, load_scoring

CONFIG_DIR = Path(__file__).resolve().parent.parent / "config"

def test_load_requirements_has_hard_filters():
    req = load_requirements(CONFIG_DIR)
    assert req["hard"]["cellular"] == "required"
    assert "native_mqtt" in req["hard"]["api"]
    assert req["benchmark"] == "Milesight UC300-L05EU"

def test_load_scoring_weights_sum_to_one():
    w = load_scoring(CONFIG_DIR)["weights"]
    assert abs(sum(w.values()) - 1.0) < 1e-9

def test_load_sources_has_cellular_tier():
    src = load_sources(CONFIG_DIR)
    assert "Milesight" in src["tiers"]["cellular_iot_controllers"]

def test_missing_file_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        load_requirements(tmp_path)
```

- [ ] **Step 3: Run test to verify it fails**

Run: `uv run pytest tests/test_research_config.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'engine.research_config'`

- [ ] **Step 4: Write the implementation**

```python
# engine/research_config.py
"""Load the YAML rule files (requirements, sources, scoring) from config/."""
from __future__ import annotations

from pathlib import Path

import yaml


def _load(config_dir: Path, name: str) -> dict:
    path = config_dir / name
    if not path.is_file():
        raise FileNotFoundError(f"Config file not found: {path}")
    return yaml.safe_load(path.read_text())


def load_requirements(config_dir: Path) -> dict:
    return _load(config_dir, "requirements.yaml")


def load_sources(config_dir: Path) -> dict:
    return _load(config_dir, "sources.yaml")


def load_scoring(config_dir: Path) -> dict:
    return _load(config_dir, "scoring_weights.yaml")
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/test_research_config.py -v`
Expected: PASS (4 passed)

- [ ] **Step 6: Commit**

```bash
git add config/ engine/research_config.py tests/test_research_config.py
git commit -m "feat: seed research config YAMLs + loader"
```

---

### Task 6: CLI

**Files:**
- Create: `engine/cli.py`
- Test: `tests/test_cli.py`

**Interfaces:**
- Consumes: `Config`, `DeviceStore`, `load_requirements`.
- Produces: `main` (click group) with commands `paths`, `db-info`, `requirements`. Entry point `engine = "engine.cli:main"` (already declared in Task 1).

- [ ] **Step 1: Write the failing test**

```python
# tests/test_cli.py
from __future__ import annotations
from click.testing import CliRunner
from engine.cli import main

def test_paths_runs(monkeypatch, tmp_path):
    monkeypatch.setenv("ENGINE_DATA_DIR", str(tmp_path / "data"))
    result = CliRunner().invoke(main, ["paths"])
    assert result.exit_code == 0
    assert "Ollama host" in result.output

def test_requirements_shows_benchmark():
    result = CliRunner().invoke(main, ["requirements"])
    assert result.exit_code == 0
    assert "UC300-L05EU" in result.output

def test_db_info_reports_count(monkeypatch, tmp_path):
    monkeypatch.setenv("ENGINE_DATA_DIR", str(tmp_path / "data"))
    result = CliRunner().invoke(main, ["db-info"])
    assert result.exit_code == 0
    assert "0" in result.output
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_cli.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'engine.cli'`

- [ ] **Step 3: Write the implementation**

```python
# engine/cli.py
"""`engine` CLI entry point."""
from __future__ import annotations

import click
from rich.console import Console
from rich.table import Table

from .config import Config
from .research_config import load_requirements
from .store import DeviceStore

console = Console()


@click.group()
def main() -> None:
    """door-hardware-sourcing-engine."""


@main.command()
def paths() -> None:
    """Print resolved config from .env."""
    cfg = Config.load()
    table = Table(show_header=False, box=None)
    table.add_row("Ollama host", cfg.ollama_host)
    table.add_row("Chat model", cfg.chat_model)
    table.add_row("Data dir", str(cfg.data_dir))
    table.add_row("Config dir", str(cfg.config_dir))
    console.print(table)


@main.command(name="db-info")
def db_info() -> None:
    """Show how many controllers are stored."""
    cfg = Config.load()
    store = DeviceStore(cfg.db_path())
    try:
        console.print(f"Controllers stored: {store.count()}")
    finally:
        store.close()


@main.command()
def requirements() -> None:
    """Print the hard/bonus criteria and the benchmark device."""
    cfg = Config.load()
    req = load_requirements(cfg.config_dir)
    console.print(f"[bold]Benchmark:[/bold] {req['benchmark']}")
    console.print(f"[bold]Hard criteria:[/bold] {req['hard']}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_cli.py -v`
Expected: PASS (3 passed)

- [ ] **Step 5: Run the full suite + the real CLI**

Run: `uv run pytest -q && uv run engine requirements`
Expected: all tests pass; `engine requirements` prints the UC300-L05EU benchmark.

- [ ] **Step 6: Commit**

```bash
git add engine/cli.py tests/test_cli.py
git commit -m "feat: engine CLI with paths, db-info, requirements"
```

---

## Done criteria for Plan 1
- `uv run pytest -q` is green.
- `uv run engine paths`, `engine db-info`, `engine requirements` all work.
- A `Controller` can be persisted to and read from SQLite, deduped by `(vendor, model)`.
- Seed config encodes the hard criteria and the UC300-L05EU benchmark.

Then proceed to **Plan 2 — Crawl + LLM extract**.
