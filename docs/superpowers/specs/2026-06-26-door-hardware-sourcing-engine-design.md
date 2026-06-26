# Design Spec — door-hardware-sourcing-engine

**Date:** 2026-06-26
**Status:** Draft for review
**Author:** William Fagher (with Claude)
**Sibling of:** `arena-research-engine`

---

## 1. Purpose

A 24/7 local-LLM research engine that finds **finished, re-brandable access-control door
hardware** and ranks the best alternatives for sourcing.

**Device concept (decided 2026-06-26):** the user already operates the access-control
*application* — the cloud brain that decides who / when / where may open a door. The hardware they
need is therefore essentially a **cellular connected relay** (Swedish *"uppkopplat relä"*): an LTE
edge node that receives an open/close command from the user's app over **MQTT or clean REST** and
fires the lock relay — plus "additional functionality" (a reader interface to forward credentials
to the app, and door I/O). The device does **not** need its own user database, local access logic,
or a proprietary vendor cloud — those would duplicate or fight the user's app. This is decisively
**Family B** in §8, not the all-in-one access terminals of Family A.

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

- **Searched category:** door controllers / access panels **only**. **Reader support
  (RFID/NFC/BLE) and electric-lock/strike compatibility are spec criteria of the controller, not
  separately searched categories.** A controller sold as a complete kit (bundled reader/lock) is
  still evaluated as a controller, tagged `bundled-kit`.
- **Geography:** Nordic/EU-first, then global (incl. Chinese ODMs that offer OEM programs).

### Scope (out, for now)

- Cloud-managed SaaS platforms (Kisi/Verkada/Brivo) as products to *resell* — only relevant if
  they sell rebrandable hardware.
- DIY/open-source ecosystems (ESPHome/ESP-RFID) — finished+CE-marked is the requirement.

---

## 2. Deliverable

The engine researches **one category: door controllers / access panels.** Reader support
(RFID/NFC) and electric-lock/strike compatibility are **criteria of each controller**, not
separately searched categories.

**Segmented shortlists** of controllers rather than one flat ranking — controllers vary widely
(standalone vs networked, single- vs multi-door, indoor vs outdoor) and unlike controllers
shouldn't be forced into one list.

- **Sub-segments within cellular connected relays** (this is what gives multiple ~top-10 lists):
  - by reader interface: relay-only vs reader-capable (Wiegand / OSDP / RS-485)
  - by door capacity: single-door (1–2 relays) vs multi-door (4+ relays)
  - by environment: indoor (IP30) vs outdoor-rated (IP65)
  - by rebrand tier: vendor OEM program vs re-case-friendly
  (final axes confirmed once `requirements.yaml` is filled)
- **Per sub-segment:** ranked **~top 10** (fewer if small), each finalist with
  **pros / cons + recommended rebrand path + CE note**, every claim cited to a source.
- **Cross-cutting tags** on each finalist so the data can be sliced: rebrand path
  (`oem_program` / `recase_diy` / `resell_as_is` / `none`), reader/credential support, lock
  compatibility, country of origin, EU stock availability.
- Backed by a **full normalized spec matrix** over *every* controller found (the structured
  dataset), from which the shortlists are derived.

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
│   ├── models.py           # Controller, ReaderSupport, LockSupport, OEMProgram, Certification (pydantic)
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

A normalized `Controller` record (the only searched category) with full spec fields
(section 4.2). Reader and lock support are embedded as controller criteria
(`ReaderSupport`, `LockSupport`), plus two purpose-specific blocks:

- `OEMProgram` — white-label offered? logo-on-product? custom firmware/UI branding? MOQ? who
  holds CE?
- `Certification` — CE / EN 60839 / RED / RoHS, Declaration of Conformity (DoC) available?

Every controller carries a `RebrandPath` enum: `oem_program | recase_diy | resell_as_is | none`,
and a `bundled-kit` tag if it ships with reader/lock included.

### Pipeline

`crawl → extract (LLM datasheet → structured record) → dedup/normalize → score → rank → report`.
Mirrors the existing `crawler → Signal → drafter` flow; "Signal" becomes "Controller record" and
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
| Global access-terminal OEM/ODM | ZKTeco, Suprema, Hikvision, Dahua, **CiVinTec**, Granding, Sebury + Shenzhen ODMs | Core of the "rebrand it" path — many explicitly offer private label; CiVinTec CT-series adds 4G + BLE/NFC |
| **Industrial cellular IoT controllers / RTUs (M2M)** | **Milesight (UC300), King Pigeon, Teracom, ControlByWeb, Robustel, NORVI, ThingsLog, Allockate** | **Where the LTE + native-MQTT + no-firmware matches actually live** — paired with a reader + lock; usually OEM/ODM-friendly. **Without this tier the engine misses the best-fit devices.** |
| Reader/credential reference | HID, Elatec, STid; MIFARE/DESFire, OSDP standards | Reference only — to judge *which readers/credentials a controller supports* (a controller criterion, not a search target) |
| Marketplaces / distributors | Alibaba, Made-in-China, Global Sources, EU distributors | MOQ, pricing, OEM terms, EU stock with existing CE |
| Certification / DoC sources | EU DoC PDFs, EN 60839-11-1, RED/CE references | Verify who holds CE and whether rebranding is offered |

### 4.2 Canonical spec schema (`config/spec_schema.yaml`)

Every **controller** normalized to comparable fields. Reader and lock support appear here as
controller *criteria* (which credentials/readers it accepts, which locks it can drive):

- **Identity:** vendor, model, category, country of origin, year
- **Credentials/RFID:** 125 kHz / 13.56 MHz (MIFARE Classic/DESFire), NFC, BLE/mobile, PIN, biometric
- **Protocols/integration:** OSDP, Wiegand, MQTT, REST API, Modbus, relay outputs (decides whether
  it runs on the user's own stack)
- **API type (verify — don't trust marketing):** `native-mqtt` vs `rest-http(s)` vs
  `vendor-cloud-only`. Many "IoT-ready" 4G access terminals speak HTTP/HTTPS *to their own cloud*,
  not MQTT to your broker — this is the field that separates a true fit from a near-miss.
- **Programmability ("no firmware coding" lives here):** `config-only` / `rules-engine`
  (e.g. Milesight's 16 edge rules) / `sdk-or-firmware-required` (e.g. Arduino-based boards).
- **Connectivity/power:** PoE, WiFi, cellular, RS-485; 12/24 V
- **Physical:** indoor/outdoor, IP/IK rating, dimensions, mounting (feeds "can I re-case it")
- **Door fit:** controller channels (1/2/4 doors), lock type supported (strike/maglock/motor)
- **Commercial:** unit price, MOQ, lead time, EU stock/distributor
- **Rebrandability:** OEM program Y/N, logo-on-device, custom firmware/UI, who holds CE, `RebrandPath`
- **Certification:** CE, EN 60839, **RED (Radio Equipment Directive — mandatory for any LTE/WiFi/BLE
  radio)**, cellular module type approval, RoHS, DoC available. Note: a built-in radio makes
  re-casing *more* regulated than a passive reader — reinforces the OEM-program path for cellular units.

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
- Build the full matrix → filter to controllers meeting hard requirements → rank by weighted
  score within each controller sub-segment → take **~top 10 per sub-segment** → LLM writes
  **pros/cons + recommended rebrand path** per finalist, each claim cited.

### Seed leads (known starting points)

- **White-label-friendly finished controllers:** ZKTeco (inBio / C3), Suprema CoreStation,
  Axis A16, Hikvision / Dahua access controllers, Shenzhen ODM access panels.
- **EU incumbents to benchmark against:** Aptus, RCO, Axema, Nedap, Gantner.

---

## 5. CLI commands

```bash
engine discover                 # crawl all configured sources → populate device DB
engine extract <url|pdf>        # one-off: pull a datasheet into a structured record
engine matrix                   # full side-by-side spec matrix of all controllers
engine shortlist --top 10       # ranked controller shortlists per sub-segment (the deliverable)
engine device <id>              # deep-dive on one device
engine scheduler                # periodic re-crawl to catch new models / price changes
```

Plus foundation commands inherited from arena-research-engine: `ping`, `paths`, `health`.

---

## 6. Open inputs (to fill before/at implementation)

- **Hard criteria confirmed (2026-06-26):**
  1. **LTE / 4G cellular connectivity — required** (hard filter; no-cellular devices are excluded).
  2. **WiFi + Bluetooth — bonus** (scoring boost, not a filter).
  3. **MQTT or equivalent ready API, no firmware coding — required** (`api_type` ∈ {native-mqtt,
     rest-http} AND `programmability` ∈ {config-only, rules-engine}).
  4. **Reader interface (Wiegand / OSDP / RS-485) to forward credentials to the app — high-value
     plus / future-proofing**, not a hard filter ("eventually add RFID readers"). Door I/O (door
     contact, REX, tamper) similarly weighted.
- **ARCHITECTURE DECIDED (2026-06-26): Family B — cellular connected relay** (see §1 device concept
  and §8). The engine targets LTE relay controllers that the user's own app commands; all-in-one
  access terminals (Family A) are out of scope except as benchmark references.
- **API rule (decided):** native MQTT **or** clean REST to the *user's own server* both qualify.
  **Vendor-cloud-only devices are excluded** — if the maker's proprietary cloud is the only way in,
  the user's app can't command it.
- **`requirements.yaml`** — remaining requirements: credential types (which RFID frequencies/standards),
  indoor/outdoor, single vs multi-door, budget per unit, acceptable MOQ, target volume.
- **Shortlist size confirmed:** ~top 10 per controller sub-segment (not one flat list).
- **Searched category confirmed:** door controllers only; reader/lock support are controller criteria.
- **Project location confirmed:** sibling folder `door-hardware-sourcing-engine`.

---

## 7. Phasing (to be turned into an implementation plan)

1. **Foundation** — scaffold project (pyproject/uv), copy `llm/`, `indexer/`, `health/`, `config.py`
   from arena-research-engine; `ping`/`paths`/`health` work.
2. **Model + schema** — `models.py`, `spec_schema.yaml`, `requirements.yaml`, device SQLite store.
3. **Crawl + extract** — vendor/distributor crawlers + LLM datasheet extraction + verification.
4. **Score + compare** — scoring rubric + segmented shortlist generator + matrix output.
5. **Always-on** — scheduler for periodic re-crawl; loop-until-dry discovery.

---

## 8. Initial landscape scouting (validated 2026-06-26)

A manual web pass against the three hard criteria (LTE + WiFi/BLE bonus + MQTT/no-firmware). The
key finding: **traditional access-control brands mostly fail these criteria** — they are LAN/PoE +
Wiegand/OSDP and locked to their own management software. The matches cluster in two families, and
this should be **validated by the engine**, not taken as final.

### Family A — All-in-one 4G access terminals (finished, reader+controller in one unit)

| Device | LTE | WiFi/BLE | API | No-firmware | Rebrand | Notes |
|--------|-----|----------|-----|-------------|---------|-------|
| **CiVinTec CT9 / CT9 Pro / CT9 E / CT10** | ✅ 4G | ✅ BLE+NFC (+WiFi on some) | HTTP/HTTPS + SDK (MQTT **unverified**) | ✅ config/SDK | ✅✅ explicit ODM: logo on screen + body, HW/FW/SW customization | IP65 outdoor, dual-freq RFID + QR, OSDP, 1–2 relays. CT10 adds GPS. **Branding = logo/faceplate, not a full re-case.** |
| CellGate Entría (E4DC) | ✅ LTE or Ethernet | — | vendor cloud (TrueCloud) | ✅ | ❌ locked to CellGate platform | US, 1/4-door, works with 3rd-party readers. Not your-own-stack. |

### Family B — Cellular IoT controllers / RTUs (native MQTT; you add a reader + lock)

| Device | LTE | WiFi/BLE | API | No-firmware | Rebrand | Notes |
|--------|-----|----------|-----|-------------|---------|-------|
| **Milesight UC300 (Cellular)** | ✅ 3G/4G | — | **native MQTT** + TCP/UDP | ✅ 16-rule edge engine | OEM-ish | Relay out, RS-485 Modbus, runs rules offline. IP30 indoor. Strong native-MQTT fit. |
| **King Pigeon (S2xx / S275)** | ✅ 4G | — | **MQTT** + Modbus | ✅ config | ✅ OEM/ODM to 100+ clients | 210+ RTU models, 4 relays, KPIIOT cloud or your broker. Classic OEM cellular RTU. |
| Teracom TCG120-4 | ✅ 4G | — | MQTT + HTTP | ✅ config | OEM-ish | EU (Bulgaria) → CE-clean. 2 relays, generic I/O. |
| ControlByWeb X-412CW | ✅ cellular | — | MQTT/Modbus/SNMP/REST | ✅ config | — | US. 4 relays. |
| NORVI X (X1/X2/X3) | ✅ optional 4G | ✅ WiFi+BT5.0 | native MQTT/HTTP | ⚠️ Arduino-programmable | ✅ OEM-focused | $79–101, ESP32-S3, 200 I/O, TFT. **"No firmware" is shaky — you'd likely code access logic.** |
| Allockate | ✅ LTE-M / Cat-1 | — | **TLS MQTT** | ✅ platform | OEM-ish | Purpose-built modular access HW: master + slave door I/O over Modbus, 8 relays, QR/keypad modules. Tied to Allockate platform. |

### Contrast — traditional panels that FAIL the criteria

- **Johnson Controls iSTAR Edge G2** — has an MQTT open-connectivity protocol + OSDP, but **Ethernet/PoE only → no LTE**; enterprise, not white-label.
- **Kantech KT-4** — Ethernet + optional WiFi, **no cellular**, locked to EntraPass software.

### Strategic implication

The deliverable's sub-segmentation should likely be **Family A vs Family B** (plus the existing
topology/door-count axes), because they represent two genuinely different sourcing strategies:

- **A = "simply put up, finished"** but branding is limited to logo/faceplate and MQTT is often
  actually HTTP-to-vendor-cloud.
- **B = "put my own case around it" + true native MQTT on your own broker**, at the cost of
  assembling controller + reader + lock and handling RED/radio approval on the re-case.

### Decision (2026-06-26)

**Family B chosen.** The user already runs the access-control app (the brain), so the device is a
cellular connected relay the app commands — not a self-contained terminal. Family A remains only as
a benchmark/contrast. Reader interface (Wiegand/OSDP/RS-485) is a high-value plus, not a hard
filter, per "eventually add RFID readers." Strongest seed candidates to validate first:
**King Pigeon** (OEM cellular RTU, MQTT, 4 relays), **Milesight UC300 Cellular** (native MQTT,
edge rules), **Teracom TCG120-4** (EU-made, CE-clean), with **Allockate** as the closest
access-specific modular option.
```
