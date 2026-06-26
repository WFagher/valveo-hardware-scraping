# Design Spec — door-hardware-sourcing-engine

**Date:** 2026-06-26
**Status:** Draft for review
**Author:** William Fagher (with Claude)
**Sibling of:** `arena-research-engine`

---

## 1. Purpose

A 24/7 local-LLM research engine that finds **finished, re-brandable access-control door
hardware** and ranks the best alternatives for sourcing.

The user wants to **buy a finished product and sell it as their own** — either via a vendor
OEM/white-label program, or by putting their own enclosure around an otherwise-unmodified
certified device — **without re-doing CE conformity assessment**. The engine therefore treats
two dimensions as first-class that a generic spec comparison would miss:

1. **Rebrandability** — does the vendor offer OEM/white-label, or is the product amenable to
   re-casing as-is?
2. **CE / regulatory cleanliness** — who legally holds the CE mark, and does the chosen rebrand
   path keep that responsibility with the original manufacturer?

> ⚠️ **Not legal advice — a research dimension.** Under EU rules, placing a product on the market
> under your own name/enclosure can make *you* the legal manufacturer and re-trigger conformity
> obligations. The lowest-risk "didn't change it, didn't re-certify" path is usually a proper
> OEM/private-label agreement where the original maker keeps responsibility. The engine ranks
> vendors by *how* they let you brand precisely because this is the crux of the goal.

### Scope (in)

- **Device categories:** door controllers/panels, RFID/NFC/BLE readers (incl. embeddable OEM
  reader modules), electric locks/strikes, and all-in-one access kits.
- **Geography:** Nordic/EU-first, then global (incl. Chinese ODMs that offer OEM programs).

### Scope (out, for now)

- Cloud-managed SaaS platforms (Kisi/Verkada/Brivo) as products to *resell* — only relevant if
  they sell rebrandable hardware.
- DIY/open-source ecosystems (ESPHome/ESP-RFID) — finished+CE-marked is the requirement.

---

## 2. Deliverable

**Segmented shortlists** rather than one flat ranking, because controllers, readers, and locks
are not comparable on one axis and each alternative has unique pros/cons.

- **Primary segments (by category):**
  1. Door controllers / panels (standalone + networked)
  2. RFID/NFC readers (incl. embeddable OEM reader modules)
  3. Electric locks / strikes
  4. All-in-one access kits ("simply put up")
- **Per segment:** ranked **~top 10** (fewer if the segment is small), each finalist with
  **pros / cons + recommended rebrand path + CE note**, every claim cited to a source.
- **Cross-cutting tags** on each finalist so the user can slice the data: rebrand path
  (`oem_program` / `recase_diy` / `resell_as_is` / `none`), use-case (indoor/outdoor,
  single-door/multi-door), country of origin, EU stock availability.
- Backed by a **full normalized spec matrix** over *every* device found (the structured dataset),
  from which the shortlists are derived.

---

## 3. Architecture

A lean clone of `arena-research-engine`. Same Ollama + RAG + crawler + scheduler + health-gate
spine; the SEO/marketing/brand-guard drafters are replaced by a structured
**spec-extraction → scoring → shortlist** pipeline.

**Reused from arena-research-engine (copy + adapt):** `llm/` (Ollama client, RAG), `indexer/`
(vector store), `health/` (thermal gate — just as needed for the 70B), `scheduler.py` skeleton,
`config.py`, `outputs/intel_vault_writer.py`.

**Replaced:** `drafters/` + `signals.py` become a device-centric model and comparison pipeline.

```
door-hardware-sourcing-engine/
├── engine/
│   ├── cli.py              # commands (section 5)
│   ├── config.py           # + OEM/distributor source paths
│   ├── scheduler.py        # periodic re-crawl of vendor/distributor catalogs
│   ├── llm/                # Ollama client + RAG  (reused)
│   ├── indexer/            # vector store for retrieval over scraped catalogs (reused)
│   ├── health/             # thermal gate (reused)
│   ├── models.py           # Device, Reader, Controller, Lock, OEMProgram, Certification (pydantic)
│   ├── crawlers/           # vendor_catalog, distributor (Alibaba/Made-in-China),
│   │                       #   datasheet_pdf, reader_module, ce_doc
│   ├── extractors/         # LLM spec-extraction: datasheet → normalized Device record
│   ├── scoring/            # rebrandability + ready-to-install + spec-fit + CE-risk rubric
│   ├── compare/            # build spec matrix + rank → segmented top-N shortlists
│   └── outputs/            # device DB (SQLite), comparison matrix (md/csv), shortlist report
├── config/
│   ├── sources.yaml        # vendors, distributors, OEM portals to crawl (section 4.1)
│   ├── spec_schema.yaml    # canonical comparable fields (section 4.2)
│   ├── scoring_weights.yaml # rebrandability vs price vs spec-fit weights (section 4.3)
│   └── requirements.yaml   # the user's hard requirements (TO BE FILLED — section 6)
├── data/                   # devices.sqlite3, vector_store.sqlite3, crawl_hashes.sqlite3
└── reports/                # generated shortlists + matrix
```

### Data model (`models.py`)

A normalized `Device` record with `category` (controller/reader/lock/kit), full spec fields
(section 4.2), plus two purpose-specific blocks:

- `OEMProgram` — white-label offered? logo-on-product? custom firmware/UI branding? MOQ? who
  holds CE?
- `Certification` — CE / EN 60839 / RED / RoHS, Declaration of Conformity (DoC) available?

Every device carries a `RebrandPath` enum: `oem_program | recase_diy | resell_as_is | none`.

### Pipeline

`crawl → extract (LLM datasheet → structured record) → dedup/normalize → score → rank → report`.
Mirrors the existing `crawler → Signal → drafter` flow; "Signal" becomes "Device record" and
"drafter" becomes "comparison/shortlist generator."

### Approaches considered

1. **(Recommended) Catalog-crawl + LLM-extract into a normalized SQLite DB** — comprehensive,
   repeatable, handles "ALL alternatives," gives a clean comparable matrix for ranking.
2. RAG-only (everything in the vector store, ask questions) — faster to build, but no clean
   matrix and weak for ranking.
3. Manual-curated YAML the LLM summarizes — most accurate per-entry, doesn't scale to "ALL,"
   goes stale.

Chosen: **#1**, with RAG (#2) layered on top for ad-hoc questions.

---

## 4. Research plan (what to compare, exactly how)

### 4.1 Source taxonomy (`config/sources.yaml`) — crawl breadth-first across five tiers

| Tier | Examples | Why |
|------|----------|-----|
| Nordic/EU incumbents | ASSA ABLOY, Aptus, RCO, Axema, Salto, Gantner, Nedap, 2N, Axis (A16 controllers + readers) | Already CE-marked, EU-legal; some have OEM lines |
| Global OEM/ODM (white-label friendly) | ZKTeco, Suprema, Hikvision, Dahua, Granding, Sebury + Shenzhen ODMs | Core of the "rebrand it" path — many explicitly offer private label |
| Reader modules (embed-in-your-own-case) | HID Global OEM cores, Elatec TWN4, STid, Identiv, RFIDeas | Designed to be built into your enclosure — the user's exact use case, lowest CE risk |
| Marketplaces / distributors | Alibaba, Made-in-China, Global Sources, EU distributors | MOQ, pricing, OEM terms, EU stock with existing CE |
| Certification / DoC sources | EU DoC PDFs, EN 60839-11-1, RED/CE references | Verify who holds CE and whether rebranding is offered |

### 4.2 Canonical spec schema (`config/spec_schema.yaml`)

Every device normalized to comparable fields:

- **Identity:** vendor, model, category, country of origin, year
- **Credentials/RFID:** 125 kHz / 13.56 MHz (MIFARE Classic/DESFire), NFC, BLE/mobile, PIN, biometric
- **Protocols/integration:** OSDP, Wiegand, MQTT, REST API, Modbus, relay outputs (decides whether
  it runs on the user's own stack)
- **Connectivity/power:** PoE, WiFi, cellular, RS-485; 12/24 V
- **Physical:** indoor/outdoor, IP/IK rating, dimensions, mounting (feeds "can I re-case it")
- **Door fit:** controller channels (1/2/4 doors), lock type supported (strike/maglock/motor)
- **Commercial:** unit price, MOQ, lead time, EU stock/distributor
- **Rebrandability:** OEM program Y/N, logo-on-device, custom firmware/UI, who holds CE, `RebrandPath`
- **Certification:** CE, EN 60839, RED, RoHS, DoC available

### 4.3 Scoring rubric (`config/scoring_weights.yaml`)

Each device scored 1–10 on each axis, then weighted:

- **Rebrandability** (highest weight): `oem_program` > `resell_as_is` > `recase_diy` > `none`
- **Ready-to-install** (finished product vs dev kit)
- **Spec-fit** vs `requirements.yaml`
- **CE/regulatory cleanliness** (lower risk = higher score)
- **Commercial** (price × MOQ × EU availability)

### 4.4 Extraction method (how the LLM is used)

- Crawler grabs product pages + datasheet PDFs (`readability-lxml` for HTML, PDF text layer for
  datasheets).
- The 70B (fast model for bulk) runs a **structured-extraction prompt**: "fill this JSON schema;
  use `null` for anything not stated — never invent a spec." Output validated by pydantic
  (mirrors the existing engine's grounded-output discipline).
- **Verification pass:** a second LLM call cross-checks each record against source text and flags
  low-confidence fields; those queue for manual confirmation rather than being trusted (same
  "cite or say you don't know" discipline as `rag.py`).
- Dedup by (vendor, model); price/availability refreshed on schedule.

### 4.5 Convergence to the shortlists

- Run discovery until **N consecutive crawl rounds surface no new vendors** (loop-until-dry).
- Build the full matrix → filter to devices meeting hard requirements → rank by weighted score
  within each segment → take **~top 10 per segment** → LLM writes **pros/cons + recommended
  rebrand path** per finalist, each claim cited.

### Seed leads (known starting points)

- **Readers (lowest CE risk for "own case"):** Elatec TWN4, HID OEM reader cores — explicitly
  built to be embedded in your own housing without re-certifying the radio.
- **Controllers (white-label-friendly finished units):** ZKTeco, Suprema, Axis A16.

---

## 5. CLI commands

```bash
engine discover                 # crawl all configured sources → populate device DB
engine extract <url|pdf>        # one-off: pull a datasheet into a structured record
engine matrix --category reader # full side-by-side spec matrix for a category
engine shortlist --top 10       # segmented ranked shortlists + pros/cons (the deliverable)
engine device <id>              # deep-dive on one device
engine scheduler                # periodic re-crawl to catch new models / price changes
```

Plus foundation commands inherited from arena-research-engine: `ping`, `paths`, `health`.

---

## 6. Open inputs (to fill before/at implementation)

- **`requirements.yaml`** — the user's hard requirements: which protocols (OSDP? REST? MQTT?),
  credential types (which RFID frequencies/standards), indoor/outdoor, single vs multi-door,
  budget per unit, acceptable MOQ, target volume. Until filled, ranking weights rebrandability +
  spec completeness and treats requirements as soft.
- **Shortlist size confirmed:** ~top 10 per segment (not one flat list).
- **Project location confirmed:** sibling folder `door-hardware-sourcing-engine`.

---

## 7. Phasing (to be turned into an implementation plan)

1. **Foundation** — scaffold project (pyproject/uv), copy `llm/`, `indexer/`, `health/`, `config.py`
   from arena-research-engine; `ping`/`paths`/`health` work.
2. **Model + schema** — `models.py`, `spec_schema.yaml`, `requirements.yaml`, device SQLite store.
3. **Crawl + extract** — vendor/distributor crawlers + LLM datasheet extraction + verification.
4. **Score + compare** — scoring rubric + segmented shortlist generator + matrix output.
5. **Always-on** — scheduler for periodic re-crawl; loop-until-dry discovery.
```
