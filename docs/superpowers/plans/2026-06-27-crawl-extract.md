# Crawl + LLM Extract Implementation Plan (Plan 2 of 5)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn web pages / datasheets into validated `Controller` records — an Ollama chat client, an HTML fetcher, an LLM spec-extractor with the "use null, never invent" discipline, and `engine ping/extract/discover` CLI commands that populate the SQLite store.

**Architecture:** A thin `OllamaClient` (httpx) is *injectable* so the extractor is fully unit-testable with a fake model. `fetch_text()` pulls a URL and strips HTML to text. `extract_controller(text, ollama=..., model=...)` prompts the model for JSON, validates it into a `Controller` (pydantic ignores extra keys; missing vendor/model or bad JSON → `None`). The CLI wires fetch → extract → `DeviceStore.upsert`.

**Tech Stack:** Python 3.12+, httpx (already a dep), pydantic, click, rich, pyyaml. No new dependencies (PDF/playwright crawling deferred to a later plan).

## Global Constraints
- `from __future__ import annotations` at the top of every module; ruff line-length 100, py312.
- Reuse `engine.models.Controller`, `engine.store.DeviceStore`, `engine.config.Config` from Plan 1.
- The extractor MUST NOT invent values: anything not stated in the source becomes `null`.
- LLM access goes only through `OllamaClient`; tests never hit a network or a live model (use `httpx.MockTransport` and a fake-ollama object).

## File Structure (this plan)
- `engine/llm/__init__.py`, `engine/llm/ollama_client.py` — `ChatMessage`, `OllamaClient`.
- `engine/crawlers/__init__.py`, `engine/crawlers/fetcher.py` — `strip_html`, `fetch_text`.
- `engine/extractors/__init__.py`, `engine/extractors/spec_extractor.py` — `build_messages`, `extract_controller`.
- `engine/cli.py` — add `ping`, `extract`, `discover`.
- `config/seed_urls.yaml` — seed product/datasheet URLs.
- Tests: `tests/test_ollama_client.py`, `tests/test_fetcher.py`, `tests/test_spec_extractor.py`, `tests/test_cli_extract.py`.

---

### Task 1: Ollama chat client

**Files:**
- Create: `engine/llm/__init__.py`, `engine/llm/ollama_client.py`
- Test: `tests/test_ollama_client.py`

**Interfaces:**
- Produces:
  - `ChatMessage(role: str, content: str)` (dataclass).
  - `OllamaClient(host="http://localhost:11434", *, timeout=120.0, transport=None)`; context manager; `chat(model, messages: list[ChatMessage], *, temperature=0.2, json_mode=False) -> str`; `ping(model) -> bool`; `close()`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_ollama_client.py
from __future__ import annotations
import httpx
from engine.llm.ollama_client import ChatMessage, OllamaClient

def _transport(captured):
    def handler(request):
        captured["payload"] = httpx.Request("POST", request.url, content=request.content).content
        return httpx.Response(200, json={"message": {"content": "hello"}})
    return httpx.MockTransport(handler)

def test_chat_returns_message_content():
    cap = {}
    with OllamaClient(transport=_transport(cap)) as ol:
        out = ol.chat("m", [ChatMessage("user", "hi")], json_mode=True)
    assert out == "hello"
    assert b'"format": "json"' in cap["payload"] or b'"format":"json"' in cap["payload"]

def test_ping_true_on_response():
    with OllamaClient(transport=_transport({})) as ol:
        assert ol.ping("m") is True

def test_ping_false_on_error():
    def handler(request):
        return httpx.Response(500, json={})
    with OllamaClient(transport=httpx.MockTransport(handler)) as ol:
        assert ol.ping("m") is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_ollama_client.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'engine.llm'`

- [ ] **Step 3: Write the implementation**

```python
# engine/llm/__init__.py
"""LLM access (Ollama)."""
from __future__ import annotations
```

```python
# engine/llm/ollama_client.py
"""Minimal Ollama chat client over httpx. Injectable transport for testing."""
from __future__ import annotations

from dataclasses import dataclass

import httpx


@dataclass
class ChatMessage:
    role: str
    content: str


class OllamaClient:
    def __init__(
        self,
        host: str = "http://localhost:11434",
        *,
        timeout: float = 120.0,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self._client = httpx.Client(
            base_url=host.rstrip("/"), timeout=timeout, transport=transport
        )

    def __enter__(self) -> "OllamaClient":
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def close(self) -> None:
        self._client.close()

    def chat(
        self,
        model: str,
        messages: list[ChatMessage],
        *,
        temperature: float = 0.2,
        json_mode: bool = False,
    ) -> str:
        payload: dict = {
            "model": model,
            "messages": [{"role": m.role, "content": m.content} for m in messages],
            "stream": False,
            "options": {"temperature": temperature},
        }
        if json_mode:
            payload["format"] = "json"
        resp = self._client.post("/api/chat", json=payload)
        resp.raise_for_status()
        return resp.json()["message"]["content"]

    def ping(self, model: str) -> bool:
        try:
            return bool(self.chat(model, [ChatMessage("user", "reply: ok")], temperature=0))
        except Exception:
            return False
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_ollama_client.py -v`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add engine/llm tests/test_ollama_client.py
git commit -m "feat: injectable Ollama chat client"
```

---

### Task 2: HTML fetcher

**Files:**
- Create: `engine/crawlers/__init__.py`, `engine/crawlers/fetcher.py`
- Test: `tests/test_fetcher.py`

**Interfaces:**
- Produces: `strip_html(html: str) -> str` (drops script/style, removes tags, collapses whitespace); `fetch_text(url: str, *, client=None, timeout=30.0) -> str` (GET, follow redirects, raise_for_status, return stripped text).

- [ ] **Step 1: Write the failing test**

```python
# tests/test_fetcher.py
from __future__ import annotations
import httpx
from engine.crawlers.fetcher import fetch_text, strip_html

def test_strip_html_removes_tags_and_scripts():
    html = "<html><head><style>x{}</style></head><body><h1>Hi</h1><script>bad()</script><p>UC300  4G</p></body></html>"
    out = strip_html(html)
    assert "Hi" in out and "UC300 4G" in out
    assert "bad()" not in out and "x{}" not in out
    assert "<" not in out

def test_fetch_text_via_mock_transport():
    def handler(request):
        return httpx.Response(200, text="<p>Milesight UC300</p>")
    client = httpx.Client(transport=httpx.MockTransport(handler))
    out = fetch_text("https://example.com/uc300", client=client)
    assert out == "Milesight UC300"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_fetcher.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'engine.crawlers'`

- [ ] **Step 3: Write the implementation**

```python
# engine/crawlers/__init__.py
"""Crawlers / fetchers."""
from __future__ import annotations
```

```python
# engine/crawlers/fetcher.py
"""Fetch a URL and reduce it to plain text for LLM extraction."""
from __future__ import annotations

import re

import httpx

_SCRIPT = re.compile(r"<(script|style)[^>]*>.*?</\1>", re.DOTALL | re.IGNORECASE)
_TAG = re.compile(r"<[^>]+>")
_WS = re.compile(r"\s+")


def strip_html(html: str) -> str:
    text = _SCRIPT.sub(" ", html)
    text = _TAG.sub(" ", text)
    return _WS.sub(" ", text).strip()


def fetch_text(url: str, *, client: httpx.Client | None = None, timeout: float = 30.0) -> str:
    owns = client is None
    client = client or httpx.Client(timeout=timeout, follow_redirects=True)
    try:
        resp = client.get(url)
        resp.raise_for_status()
        return strip_html(resp.text)
    finally:
        if owns:
            client.close()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_fetcher.py -v`
Expected: PASS (2 passed)

- [ ] **Step 5: Commit**

```bash
git add engine/crawlers tests/test_fetcher.py
git commit -m "feat: HTML fetcher with tag/script stripping"
```

---

### Task 3: LLM spec extractor

**Files:**
- Create: `engine/extractors/__init__.py`, `engine/extractors/spec_extractor.py`
- Test: `tests/test_spec_extractor.py`

**Interfaces:**
- Consumes: `engine.models.Controller`, `engine.llm.ollama_client.ChatMessage`.
- Produces: `build_messages(text: str) -> list[ChatMessage]`; `extract_controller(text: str, *, ollama, model: str, source_url: str | None = None) -> Controller | None`. `ollama` is any object with `.chat(model, messages, *, temperature=..., json_mode=...) -> str`. Returns `None` on bad JSON or missing vendor/model or pydantic validation error.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_spec_extractor.py
from __future__ import annotations
import json
from engine.extractors.spec_extractor import build_messages, extract_controller

class FakeOllama:
    def __init__(self, response: str):
        self.response = response
        self.calls = 0
    def chat(self, model, messages, **kw):
        self.calls += 1
        return self.response

def test_build_messages_has_system_and_user():
    msgs = build_messages("UC300 4G LTE MQTT")
    assert msgs[0].role == "system" and "never invent" in msgs[0].content.lower()
    assert "UC300 4G LTE MQTT" in msgs[-1].content

def test_extract_valid_record():
    resp = json.dumps({
        "vendor": "Milesight", "model": "UC300-L05EU", "cellular": True,
        "api_type": "native_mqtt", "lock": {"relay_count": 2},
        "reader": {"rs485": True}, "cert": {"ce": True, "red": True},
    })
    c = extract_controller("...", ollama=FakeOllama(resp), model="m",
                           source_url="https://x/uc300")
    assert c is not None
    assert c.vendor == "Milesight" and c.lock.relay_count == 2
    assert c.reader.rs485 is True and c.api_type.value == "native_mqtt"
    assert "https://x/uc300" in c.sources

def test_extract_strips_code_fences():
    resp = "```json\n" + json.dumps({"vendor": "Teracom", "model": "TCG120-4"}) + "\n```"
    c = extract_controller("t", ollama=FakeOllama(resp), model="m")
    assert c is not None and c.vendor == "Teracom"

def test_extract_missing_vendor_returns_none():
    c = extract_controller("t", ollama=FakeOllama(json.dumps({"model": "X"})), model="m")
    assert c is None

def test_extract_bad_json_returns_none():
    assert extract_controller("t", ollama=FakeOllama("not json"), model="m") is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_spec_extractor.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'engine.extractors'`

- [ ] **Step 3: Write the implementation**

```python
# engine/extractors/__init__.py
"""LLM extractors."""
from __future__ import annotations
```

```python
# engine/extractors/spec_extractor.py
"""Extract a structured Controller record from source text via the LLM."""
from __future__ import annotations

import json

from ..llm.ollama_client import ChatMessage
from ..models import Controller

_SYSTEM = (
    "You extract the specs of a cellular door-access controller from the text provided. "
    "Fill ONLY the requested JSON keys. Use null for anything NOT explicitly stated in the "
    "text — never invent a value. Return ONLY a JSON object, no prose."
)

_KEYS = (
    "vendor, model, sku, country_of_origin, cellular (bool), cellular_tech, wifi (bool), "
    "bluetooth (bool), ethernet (bool), api_type (native_mqtt|rest_http|vendor_cloud_only|unknown), "
    "protocols (list of strings), programmability (config_only|rules_engine|sdk_required|unknown), "
    "own_broker (bool), digital_inputs (int), ip_rating, price_eur (number), "
    "lock (object: relay_count int, relay_rating), reader (object: wiegand, osdp, rs485, rs232 booleans), "
    "cert (object: ce, red booleans)"
)


def build_messages(text: str) -> list[ChatMessage]:
    user = (
        f"Extract the controller spec. Return JSON with these keys (null if unknown):\n{_KEYS}\n\n"
        f"TEXT:\n{text}"
    )
    return [ChatMessage("system", _SYSTEM), ChatMessage("user", user)]


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
    if source_url:
        sources = data.get("sources") or []
        if source_url not in sources:
            sources.append(source_url)
        data["sources"] = sources
    try:
        return Controller.model_validate(data)
    except Exception:
        return None
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_spec_extractor.py -v`
Expected: PASS (5 passed)

- [ ] **Step 5: Commit**

```bash
git add engine/extractors tests/test_spec_extractor.py
git commit -m "feat: LLM spec extractor (text -> validated Controller)"
```

---

### Task 4: CLI — ping, extract, discover

**Files:**
- Create: `config/seed_urls.yaml`
- Modify: `engine/cli.py`
- Test: `tests/test_cli_extract.py`

**Interfaces:**
- Consumes: `OllamaClient`, `fetch_text`, `extract_controller`, `DeviceStore`, `Config`.
- Produces CLI commands:
  - `ping` — checks the chat model responds.
  - `extract TARGET` — TARGET is a local file path (read directly) or a URL (fetched); extracts and upserts one controller.
  - `discover` — reads `config/seed_urls.yaml` (`urls: [...]`), extracts each, upserts, prints a summary.

- [ ] **Step 1: Create the seed URL file**

```yaml
# config/seed_urls.yaml
urls:
  - https://www.milesight.com/iot/product/iot-controller/uc300
  - https://www.teracomsystems.com/cellular/4g-lte-wireless-io-module-tcg120-4/
  - https://controlbyweb.com/cellular/
```

- [ ] **Step 2: Write the failing test**

```python
# tests/test_cli_extract.py
from __future__ import annotations
from click.testing import CliRunner
import engine.cli as cli
from engine.models import Controller
from engine.store import DeviceStore

class _DummyOllama:
    def __init__(self, *a, **k): pass
    def __enter__(self): return self
    def __exit__(self, *e): pass
    def chat(self, *a, **k): return "{}"

def test_extract_from_file_upserts(monkeypatch, tmp_path):
    monkeypatch.setenv("ENGINE_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setattr(cli, "OllamaClient", _DummyOllama)
    monkeypatch.setattr(
        cli, "extract_controller",
        lambda text, **kw: Controller(vendor="Milesight", model="UC300-L05EU", cellular=True),
    )
    src = tmp_path / "uc300.txt"
    src.write_text("Milesight UC300 4G LTE MQTT")
    result = CliRunner().invoke(cli.main, ["extract", str(src)])
    assert result.exit_code == 0
    assert "Milesight" in result.output

    from engine.config import Config
    store = DeviceStore(Config.load().db_path())
    try:
        assert store.count() == 1
    finally:
        store.close()

def test_extract_handles_no_record(monkeypatch, tmp_path):
    monkeypatch.setenv("ENGINE_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setattr(cli, "OllamaClient", _DummyOllama)
    monkeypatch.setattr(cli, "extract_controller", lambda text, **kw: None)
    src = tmp_path / "empty.txt"
    src.write_text("nothing useful")
    result = CliRunner().invoke(cli.main, ["extract", str(src)])
    assert result.exit_code == 0
    assert "No controller" in result.output
```

- [ ] **Step 3: Run test to verify it fails**

Run: `uv run pytest tests/test_cli_extract.py -v`
Expected: FAIL — `AttributeError: module 'engine.cli' has no attribute 'OllamaClient'`

- [ ] **Step 4: Extend `engine/cli.py`** — add these imports near the top (after existing imports) and the three commands before the `if __name__` block:

```python
# add to imports in engine/cli.py
from pathlib import Path

from .crawlers.fetcher import fetch_text
from .extractors.spec_extractor import extract_controller
from .llm.ollama_client import OllamaClient
```

```python
# add these commands to engine/cli.py (before `if __name__ == "__main__":`)
@main.command()
def ping() -> None:
    """Check the Ollama chat model responds."""
    cfg = Config.load()
    with OllamaClient(cfg.ollama_host) as ol:
        ok = ol.ping(cfg.chat_model)
    console.print(f"Ollama {cfg.chat_model}: {'[green]OK[/green]' if ok else '[red]no response[/red]'}")


def _read_target(target: str) -> str:
    p = Path(target)
    if p.is_file():
        return p.read_text()
    return fetch_text(target)


@main.command()
@click.argument("target")
def extract(target: str) -> None:
    """Extract one controller from a file path or URL and store it."""
    cfg = Config.load()
    text = _read_target(target)
    with OllamaClient(cfg.ollama_host) as ol:
        controller = extract_controller(text, ollama=ol, model=cfg.chat_model, source_url=target)
    if controller is None:
        console.print("[yellow]No controller extracted.[/yellow]")
        return
    store = DeviceStore(cfg.db_path())
    try:
        store.upsert(controller)
    finally:
        store.close()
    console.print(f"[green]Stored:[/green] {controller.vendor} {controller.model}")


@main.command()
def discover() -> None:
    """Extract controllers from every URL in config/seed_urls.yaml."""
    import yaml

    cfg = Config.load()
    urls = yaml.safe_load((cfg.config_dir / "seed_urls.yaml").read_text())["urls"]
    store = DeviceStore(cfg.db_path())
    stored = 0
    try:
        with OllamaClient(cfg.ollama_host) as ol:
            for url in urls:
                text = fetch_text(url)
                controller = extract_controller(text, ollama=ol, model=cfg.chat_model, source_url=url)
                if controller is not None:
                    store.upsert(controller)
                    stored += 1
                    console.print(f"  [green]+[/green] {controller.vendor} {controller.model}")
                else:
                    console.print(f"  [yellow]-[/yellow] {url}")
    finally:
        store.close()
    console.print(f"Discovered {stored}/{len(urls)} controllers.")
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/test_cli_extract.py -v`
Expected: PASS (2 passed)

- [ ] **Step 6: Run full suite + lint**

Run: `uv run pytest -q && uv run ruff check engine tests`
Expected: all pass; ruff clean.

- [ ] **Step 7: Commit**

```bash
git add engine/cli.py config/seed_urls.yaml tests/test_cli_extract.py
git commit -m "feat: ping/extract/discover CLI commands"
```

---

## Done criteria for Plan 2
- `uv run pytest -q` green (Plan 1 + Plan 2 tests).
- The extract pipeline (fetch → LLM → validated Controller → store) works with an injected fake model.
- `engine ping`, `engine extract <file|url>`, `engine discover` exist; a live run needs Ollama up.

Then proceed to **Plan 3 — Score + segmented shortlist**.
