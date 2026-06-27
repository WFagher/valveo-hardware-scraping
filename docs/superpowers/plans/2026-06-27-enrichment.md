# Search-Backed Enrichment Implementation Plan (Plan 6)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans. Steps use checkbox (`- [ ]`) syntax.

**Goal:** Fill the fields a product-spec scrape can't provide (country-of-origin, OEM/white-label, CE/RED, rebrand path) with **real, cited** data: per device → keyless web search → fetch top results → LLM extracts only those fields → merge into the controller, recording source URLs. Same "cite it or leave it unknown" discipline as the rest of the engine.

**Architecture:** `search.web_search(query)` hits DuckDuckGo's keyless HTML endpoint and returns result URLs. `enrich.enrich_controller(c, ...)` builds 3 queries from vendor+model, fetches the top pages, runs `extract_enrichment` (an LLM call scoped to the sourcing/compliance fields), and merges **only into currently-unknown fields** (never overwrites confirmed data), appending sources. Searcher + fetch + ollama are injected so tests need no network/model. Graceful: any search/fetch failure leaves the device unchanged (still ❓).

**Tech Stack:** Python 3.12+, httpx, existing modules. No new deps, no API keys, no infra.

## Global Constraints
- `from __future__ import annotations`; ruff line-length 100, py312.
- Enrichment only **fills** fields that are None/unknown; it must not overwrite extracted spec data.
- Every enriched field's source URL is recorded in `controller.sources`.
- Tests never touch the network or a live model.

## File Structure
- `engine/crawlers/search.py` — `web_search`.
- `engine/extractors/enrich_extractor.py` — `build_enrich_messages`, `extract_enrichment`.
- `engine/enrich.py` — `enrich_controller`, `_merge`.
- `engine/cli.py` — `enrich [KEY]`.
- Tests: `tests/test_search.py`, `tests/test_enrich.py`.

---

### Task 1: Keyless web search

**Interfaces:** `web_search(query: str, *, max_results=5, client=None) -> list[str]` — DuckDuckGo HTML results, redirect-decoded, deduped; returns `[]` on any error.

- [ ] Test: a MockTransport returning sample DDG HTML yields the expected decoded URLs; a 500 yields `[]`.
- [ ] Implement `engine/crawlers/search.py` (regex over `result__a` links + `uddg=` redirect decode, browser User-Agent, try/except → `[]`).
- [ ] Commit.

### Task 2: Enrichment extractor

**Interfaces:** `extract_enrichment(text, *, ollama, model) -> dict` — keys `country_of_origin, ce, red, oem_offered, oem_moq, rebrand_path`; `{}` on bad JSON.

- [ ] Test with a fake ollama returning enrichment JSON → parsed dict; bad JSON → `{}`.
- [ ] Implement `engine/extractors/enrich_extractor.py` ("use null if not stated, never invent").
- [ ] Commit.

### Task 3: Merge + orchestrate

**Interfaces:** `enrich_controller(c, *, ollama, model, searcher=web_search, fetch=fetch_text, max_pages=3) -> Controller` — fills only unknown fields, records sources.

- [ ] Test: fake searcher/fetch/ollama → origin/ce/oem/rebrand filled, sources recorded, an already-set field NOT overwritten, empty search → unchanged.
- [ ] Implement `engine/enrich.py`.
- [ ] Commit.

### Task 4: CLI

**Interfaces:** `enrich [KEY]` — enrich one device by key or all stored; upsert results.

- [ ] Test: seed a device, monkeypatch `enrich_controller`, run `enrich` → store updated, output shown.
- [ ] Add command to `engine/cli.py`.
- [ ] Full suite + ruff + commit.

## Done criteria
- `uv run pytest -q` green.
- `engine enrich` fills OEM/CE/origin/rebrand from cited web sources, leaving genuinely-unknown fields as ❓.
