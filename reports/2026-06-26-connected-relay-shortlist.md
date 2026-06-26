# Connected-relay door controllers — verified shortlist (2026-06-26)

Output of a deep-research pass (fan-out search → fetch → 3-vote adversarial verification → synthesis)
against the Family-B brief: **LTE + MQTT/clean-REST-to-own-server + config-only + relay output**.

> **Status: verified top 3, not a full top-10.** The verification phase was throttled by transient
> API rate-limiting, so many claims (all Teltonika models, the CE/RED analysis, exact relay counts
> for two devices) ended **unverified (0-0 abstain) — not refuted**. Treat this as a confirmed
> short-shortlist plus a to-do list, and re-run a focused pass to complete it.

Run stats: 6 angles · 25 sources fetched · 97 claims → 25 verified → 10 confirmed / 15 killed.

---

## Verified top 3 (cleared 3-vote adversarial verification)

### 1. Milesight UC300 (Cellular) — strongest verified all-rounder ✅

- **Origin:** China (Milesight, Xiamen). **EU SKU: UC300-L05EU** (sold by EU distributor Landatel).
- **Cellular:** 4G LTE Cat 1 + WCDMA/GSM fallback. EU bands B1/B3/B5/B7/B8/B20/B38/B40/B41.
- **Control API:** **native MQTT** (point at *your own* broker — address/port/client-id/user/pass +
  TLS — via the ToolBox config UI, **no firmware coding**). Documented driving relay **DO1 over MQTT**
  with hex payload `7e0508001001017e`. Also TCP/UDP. Self-hosted Mosquitto confirmed by an
  independent integrator → **not cloud-locked**.
- **Relays / door I/O:** **2× SPDT relay** (3A@30VDC / 250VAC) + **4 opto-isolated digital inputs**
  (usable for door contact / REX / tamper) + **RS-485 Modbus** (a plausible future reader path).
- **Enclosure:** IP30 metal — **indoor**.
- **Pros:** cleanest verified MQTT→relay path; EU SKU exists; door inputs built in; RS-485 for a
  future OSDP/Modbus reader; runs edge rules offline.
- **Cons:** indoor only (no verified IP65); no WiFi/BLE; no native Wiegand reader; China origin
  (OEM terms unverified).
- **Rebrand path:** vendor OEM/ODM (Milesight does ODM) — **terms to confirm**.

### 2. ControlByWeb X-4xx-CW (e.g. X-412CW) — most open protocols, US-made ✅

- **Origin:** USA (Xytronix, Utah).
- **Cellular:** embedded **LTE-M (Cat-M1)** + eUICC/**eSIM multi-carrier**. (Low-throughput IoT 4G —
  fine for relay command/control, not bandwidth.)
- **Control API:** **REST + Modbus/TCP + MQTT 3.1.1 + SNMP**, user-configurable broker (up to two,
  TLS client certs). **Cloud is optional**; on-device no-code logic; built-in web server.
- **Relays:** ⚠️ exact count/rating **UNVERIFIED** — the "4 outputs, 28VAC/24VDC, 1A" claim failed
  1-0. The X-4xx line has relays, but **confirm the datasheet before sourcing**.
- **Pros:** most vendor-neutral protocol set; genuinely no cloud lock-in; US-made (no China-origin
  concern); logic survives network loss.
- **Cons:** LTE-M low bandwidth; relay spec unconfirmed; US vendor → check EU RED/CE + EU cellular
  bands; likely **no white-label program** (US industrial vendors rarely offer it); higher price.
- **Rebrand path:** likely **DIY re-case** — verify.

### 3. Teracom TCG120-4 — EU-made (cleanest CE story), relay spec to confirm ✅

- **Origin:** **Bulgaria (EU)** → cleanest CE/RED footprint; EU band tables via distributors.
- **Cellular:** 4G LTE Cat 1 + 3G/2G fallback (**2G/3G being sunset in the EU — rely on 4G**).
- **Control API:** **MQTT 3.1.1 + HTTP API** + periodic XML/JSON HTTP(S) POST to *your* server.
  Broker/server params user-entered; relays fire via SMS / HTTP API / MQTT. **No required Teracom cloud.**
- **Relays:** ⚠️ the "2 outputs NO+NC" claim was **REFUTED 1-0** — **confirm exact relay count**.
- **Pros:** EU-made = best CE/RED + EU-stock story; your-own-server; several control paths.
- **Cons:** relay count unconfirmed; 2G/3G sunset; small vendor; OEM terms/pricing unknown.
- **Rebrand path:** EU OEM relationship most plausible for a clean CE chain — verify.

---

## Side-by-side (verified facts only)

| | Milesight UC300 Cellular | ControlByWeb X-4xx-CW | Teracom TCG120-4 |
|---|---|---|---|
| Origin | China (EU SKU) | USA | **Bulgaria (EU)** |
| Cellular | 4G LTE Cat 1 (+3G/2G) | LTE-M (Cat-M1) | 4G LTE Cat 1 (+3G/2G) |
| Own-broker MQTT | ✅ documented | ✅ (also REST/Modbus/SNMP) | ✅ MQTT + HTTP API |
| No-firmware / config-only | ✅ | ✅ | ✅ |
| Relay (verified) | ✅ 2× SPDT 3A | ⚠️ unverified count | ⚠️ refuted, recheck |
| Door inputs | ✅ 4× DI | unverified | unverified |
| WiFi / BLE | ❌ | ❌ | ❌ |
| Reader iface | RS-485 (no native Wiegand) | unverified | unverified |
| IP65 outdoor | ❌ IP30 | unverified | unverified |
| OEM / price / MOQ | unverified | unverified | unverified |

All three are effectively **"relay-only"** on verified evidence; **none** confirmed a native
Wiegand/OSDP reader interface (Milesight's RS-485 is the closest path). The reader-capable vs
relay-only sub-grouping the brief asked for needs the second pass.

---

## Unverified (knocked out by rate-limiting — NOT excluded)

- **Teltonika RUT956 / TRB246 / TRB142** (Lithuania, EU) — strong EU vendor with RutOS MQTT
  publisher + I/O on some models. Claims went **0-0 (abstain)** because verifier agents were
  rate-limited. RUT956 relay control appeared only via local `ubus` CLI on the cited page — the
  remote MQTT/HTTP I/O path needs confirming. **Worth a targeted re-verify; could legitimately join
  the shortlist.**
- **King Pigeon, Robustel R1520, Tibbo, PUSR** — surfaced but produced no surviving verified claims.

## Open items for the second pass

1. Exact **relay count / contact type / rating** for ControlByWeb X-412CW and Teracom TCG120-4.
2. **Reader interface** (Wiegand/OSDP/RS-485) per device → enables the reader-capable sub-group.
3. **OEM/white-label terms, MOQ, unit price, country of origin, IP65 options** for all candidates +
   the Chinese ODMs (King Pigeon, Alibaba/Made-in-China).
4. **CE/RED re-casing analysis** — directionally: re-enclosing a CE/RED cellular device likely makes
   *you* the manufacturer of a new "final radio product" (re-triggering conformity), so a **vendor
   OEM logo/enclosure program is the cleaner path** than DIY re-case. This was **0-0 unverified** and
   needs authoritative (notified-body / RED-guidance) confirmation.
5. Re-verify **Teltonika** remote-I/O-over-own-broker.

## Key sources (verified findings)

- Milesight UC300: product page, cellular user guide, MQTT support KB, innon.com integrator note.
- ControlByWeb: `/cellular/`, `/x412/`, `/mqtt-relays/`, Mosquitto integration PDF (2025).
- Teracom: product page + TCG120-4G manual (R1.14, Apr 2025).
