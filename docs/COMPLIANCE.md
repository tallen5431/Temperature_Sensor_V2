# ThermaHub — Compliance, Certification & B2B Selling Guide

> **Not legal advice.** This is a practitioner's map of what it takes to sell a Wi-Fi
> temperature/humidity device, based on regulator and standards-body sources (2022–2026).
> Confirm specifics with a test lab / compliance consultant for your exact design and markets.
> Where a figure is a rough range, it's marked as such.

## The one-paragraph version

There are **three different things** people mean by "certified," and conflating them is the
most common (and legally risky) mistake:

1. **Mandatory radio/EMC authorization** — you *must* do this to legally sell any Wi-Fi hardware
   (US: FCC; EU: CE/RED). This is a fixed, unavoidable cost, mostly independent of who buys it.
2. **Measurement credibility (calibration)** — makes your accuracy claim defensible. Optional,
   laddered, and a *sales* lever — not a licence to sell.
3. **Regulated end-use certification** (vaccine, pharma, accredited cold-chain) — gated by
   per-unit accredited calibration and validated software. **Effectively closed** to a solo maker
   without a funded, separate product line. Don't claim it.

**Certifications are mostly a business/process investment, not a coding task.** The product
changes that *do* help (audit trail, serials, access control) are modest and several already ship.

---

## 1. Mandatory to sell ANY Wi-Fi hardware

Using a **pre-certified ESP32 module** (e.g. ESP32-WROOM-32E) carries the *intentional-radiator*
approval, which saves the biggest cost — but the **finished product is still not exempt.**

### United States — FCC (do this first, for every market segment)

| Requirement | What it takes | Effort / cost |
|---|---|---|
| **FCC Part 15 Subpart B authorization** of the finished host via **Supplier's Declaration of Conformity (SDoC)** | Test the assembled unit as a Class B *unintentional* radiator (ANSI C63.4), keep a signed test report, self-declare. **No** TCB grant, FCC ID, or filing fee — but the responsible party **must be a US-located entity.** | Medium. ~$300–900 for a truly simple build; **$1,000–3,000+** for a multi-port hub; 2–4+ weeks. |
| **Labeling** | Exterior of every unit: **"Contains FCC ID: [module's ID]"** + the two-part §15.19(a)(3) statement. May go in the manual / e-label for tiny surfaces (KDB 784748). | Low — procedural, but legally required and commonly missed. |
| **RF-exposure (MPE) + module integration conditions** | Carries over **only if** you use the certified module (not a bare SoC), keep the approved antenna, and follow Espressif's KDB 996369 integration guidance. A design change can force a Class II Permissive Change. | Low. |

> Selling an unauthorized Part 15 device is unlawful (forfeitures/seizure) and gets you delisted
> by Amazon-class marketplaces. **This is the single unavoidable gate.**

### European Union — CE marking (only if you want the EU)

| Requirement | What it takes | Effort |
|---|---|---|
| **CE under RED 2014/53/EU** (self-declaration, no Notified Body) | A Wi-Fi device is "radio equipment," so RED is the single governing directive (absorbs EMC + safety — LVD objectives apply even at 5 V USB). Test to **EN 300 328** (radio), **EN 301 489-1/-17** (EMC), **EN IEC 62368-1** (safety). Cite the exact OJEU-listed edition of each. | High. ~$700–3,000 self-cert (vs $5k–15k+ only if a Notified Body is forced). Keep the DoC + technical file 10 yr. |
| **RED cybersecurity** (Art 3.3(d)/(e) via **EN 18031-1/-2**, mandatory since **1 Aug 2025**) | Network protection + privacy for an internet-connected radio. **Design constraint:** you *lose* presumption of conformity if the device allows operation with a blank/defeatable default password — so ship **no defeatable default credentials and force a password at setup.** | Medium — and it drives a product requirement (see §5). |
| **RoHS** (DoC) **+ REACH SVHC / SCIP** | RoHS is self-assessed via the DoC. REACH is separate: if any part contains a Candidate-List SVHC > 0.1% w/w, you have mandatory supply-chain communication **and an ECHA SCIP database filing** (a real recurring obligation). | Medium. |
| **EU/UK responsible person** | A US solo maker **cannot** be the EU Art 4 economic operator — you must appoint an EU authorised rep / importer / fulfilment service, whose name + address is on the product. | Medium (ongoing). |
| **WEEE** producer registration + crossed-out-bin mark | Per-country registration in the EU; also UK. | Medium (ongoing). |

### Other markets
- **UK (GB):** CE is accepted indefinitely (no separate UKCA needed) + a GB responsible person. Low.
- **Canada (ISED):** "Contains IC: [module IC number]" + ICES-003. Low — only if selling there.

---

## 2. Calibration & accuracy claims (credibility, not a licence)

**Calibration is a sales lever, laddered in three tiers.** Ladder up as buyers demand it:

1. **Manufacturer conformance statement (weakest).** Advertise the DS18B20 honestly as
   **"±0.5 °C typical (−10 to +85 °C), uncalibrated."** Resolution (0.0625 °C) is *not* accuracy.
2. **NIST-traceable per-unit certificate** — documents the traceable reference and the measured
   variance at each point.
3. **ISO/IEC 17025 *accredited* certificate (only independently audited tier)** — valid only
   within the lab's published scope.

### The zero-cost credibility play: SHT4x
Sensirion **individually calibrates every SHT4x** with a serial-numbered **3-point ISO/IEC
17025-accredited** temperature cal (Swiss SCS 0158); per-serial certs are downloadable. So the
**grow/humidity variant can ship with a genuine per-unit accredited T/RH certificate _without you
owning a lab_** (±0.1 °C / ±1.0 %RH typ; note RH accuracy dominates derived-VPD error). For buyers
who need more, offer a **paid per-unit outsourced accredited cal** (Onset/ThermoWorks-style,
~$140 for a 3-point cert, 1–2 wk).

### Honesty lines you must not cross
- **"NIST-traceable"** describes a measurement *result*, not an instrument/lab. Never call a probe
  "NIST certified" and never imply **NIST endorsement** — NIST approves/certifies nothing.
- An in-house **ice-bath check is a *verification*, not a calibration** — no uncertainty budget,
  no span/linearity/drift. Label it *"verified at 0 °C ice point to within X °C,"* never a
  "NIST-traceable calibration certificate."
- Regulated buyers need **per-unit serialized** certs, not batch/representative ones.
- Pt100/IEC 60751 class claims need 4-wire wiring / low self-heating the ESP32 front-end usually
  won't deliver — don't overclaim.

---

## 3. Regulated end-uses — feasibility

| Standard / regime | Feasibility for a solo maker | Why |
|---|---|---|
| **US CDC/VFC vaccine storage (DDL)** | **Closed** | Hardware can hit the spec (buffered probe, ±0.5 °C, min/max, alarms), but it requires a **current per-serial NIST-traceable cert from an accredited lab on every unit** + recert every 2–3 yr. The cert logistics, not the electronics, are the wall. |
| **Pharma/clinical GxP — 21 CFR Part 11 / EU Annex 11 / GAMP 5** | **Closed** | Needs enforced per-user identity, e-signatures, tamper-evident audit trail, **validated** software (IQ/OQ/PQ), ALCOA+. A raw local CSV is the wrong substrate; the customer must also validate their install. |
| **EU EN 12830 / EN 13485** (cold-chain recorders/thermometers) | **Hard** | Sensors can meet the numbers, but a conformity *claim* requires passing the standard's full test regime (accredited test house) + EN 13486 periodic verification. Investment-gated. |
| **US food-service HACCP / FDA Food Code 2022; EU 852/2004** | **Feasible now** | Continuous electronic logging is *accepted and encouraged*; **no third-party device certification is mandated.** The legal duty is on the operator and the records. |

**Rule:** sell into HACCP as a **"temperature-logging / HACCP-support aid,"** never as a "validated
critical-control device." Never represent the product as VFC / Part 11 / EN 12830 compliant
without the full accredited-cal + validated-software + third-party-testing investment.

---

## 4. What you can reasonably sell into (tiered by effort)

| Tier | Segments | What buyers actually require | Channel |
|---|---|---|---|
| **Low bar** ✅ | Data centers / IT / server rooms / homelab / MSP sites; indoor grow / cannabis / greenhouse; museums / archives / warehouses / property mgmt; non-CCP food/brewery process | No certified-instrument mandate (ASHRAE TC 9.9, ASHRAE museum guidance, VPD agronomy are *voluntary*). They want reliability, alerts, history/CSV, and — a real differentiator — **no-cloud/on-prem** data. Procurement still asks for a **Certificate of Insurance** (CGL ~$1M/occ, $2M agg + products) and a **W-9**. | Direct/batch online first (full margin); then **MSPs** (recurring monitoring — great fit for the no-cloud angle) and **VARs**. |
| **Medium** ⚠️ | Food service (restaurants, walk-ins) — HACCP support; general (non-GxP) cold storage | Sell as a monitoring **aid**. Buyers increasingly want a **per-unit calibration option**, daily-check/annual-cal workflow, records with observation/time/observer, insurance cert, and audit-trail features if the log becomes the official record. | Direct + VARs; food-safety consultants as referral partners. |
| **High / closed** ⛔ | Vaccine (VFC), pharma GxP/GDP, clinical, accredited cold-chain | Per-unit accredited NIST-traceable cal + recert; validated tamper-evident/RBAC/e-sign software + IQ/OQ/PQ; accredited conformity testing. **None met by hardware alone.** | Don't — unless funding a deliberate validated product line. |

**Security-sensitive buyers are a hidden pocket of the low-bar tier:** IT/OT, finance, and gov
sites that deliberately choose **air-gapped / on-prem** monitoring. The local-first architecture is
a *feature* to them, not a limitation — lead with it.

---

## 5. Product features that help B2B procurement

**Already shipped (use them in the pitch):**
- ✅ **Per-unit serial numbers** — the `ThermaProbe-<HEX6>` ID, derived from the probe's unique
  DS18B20 sensor ROM (with an ESP32-MAC fallback) and persisted in NVS, is a stable per-unit serial,
  surfaced in the UI, exports, `/status`, and on the label (so per-unit cal certs can be tied to it).
- ✅ **Tamper-evident audit trail** — hash-chained, append-only log of config changes and data
  exports (`logs/audit.log`); integrity check at `GET /api/audit/verify`. The foundation any future
  Part-11 aspiration builds on, and a procurement differentiator now.
- ✅ **Access control** — optional dashboard login (`ui_auth`) with no defeatable default (also the
  shape EU RED EN 18031 requires).
- ✅ **Calibration** — per-probe offset/gain; ships alongside the SHT4x per-unit accredited cert story.
- ✅ **Configurable alarms + min/max + logging interval**, local-first, CSV export.

**Remaining for higher tiers (deliberate investment, not incidental):**
- Enforced **per-user accounts + RBAC** and **e-signatures** (Part 11).
- **Signed/hashed exports** carrying device serial + firmware version + checksum.
- **Calibration record fields** in-app (cert ref, date, points, uncertainty, next-recal-due).
- **Validated software** with IQ/OQ/PQ documentation; **data retention/backup** controls (~5 yr).
- **Buffered-probe** hardware option for food/cold-storage.

---

## 6. Staged roadmap (walk it in order)

- **Phase 0 — clear the one gate.** FCC Part 15B **SDoC** on the finished host (budget $1–3k for a
  multi-port hub), a US responsible party, and the "Contains FCC ID" + §15.19(a)(3) labeling.
  Confirm you stay inside the module's integration conditions + RF-exposure. *Unlocks the entire US
  low-bar market at minimum cost.*
- **Phase 1 — sell US-only into LOW-bar segments, direct/batch.** Homelab/IT, grow/greenhouse
  (T/RH/VPD via SHT4x), museums/warehouses. Lead with **"no cloud, data stays on your LAN"** as a
  security feature. Ship SHT4x with its free per-unit accredited cert; quote DS18B20 honestly.
  Get **product-liability insurance (CGL $1M/$2M + products)** and a **W-9** to clear procurement.
- **Phase 2 — add the calibration OPTION + light B2B controls → MEDIUM tier** (HACCP support):
  paid per-unit outsourced accredited cal (~$140), plus the already-shipped access control + audit
  trail. Market as an aid, never a validated device.
- **Phase 3 — only if you want the EU/UK.** RED self-declaration (EN 300 328 / 301 489 / 62368-1)
  **plus** RED cybersecurity (EN 18031 — force a password), RoHS DoC + REACH/SCIP, an EU (and GB)
  responsible person, and per-country WEEE. Sequence after Phase 1–2 revenue justifies the spend.
- **Phase 4 — decide, don't drift, on regulated segments.** Vaccine/VFC and pharma GxP are closed
  without per-unit accredited cal + recert and a validated software fork. Enter **only** as a
  funded, separate product line — otherwise stay out and never represent compliance you don't have.

---

## 7. Key sources
- FCC KDB 996369 (module integration), 47 CFR 15.19/15.101/2.1077, KDB 896810 (SDoC) & 784748 (labeling).
- RED 2014/53/EU + EN 300 328 / EN 301 489 / EN IEC 62368-1; Delegated Reg (EU) 2022/30 + EN 18031-1/-2:2024 + Implementing Decision (EU) 2025/138 (password rule).
- Reg (EU) 2019/1020 Art 4 (EU responsible person); WEEE; UK PSM Regs 2024 (CE accepted in GB); Canada RSS-Gen/RSS-247/ICES-003.
- RoHS 2011/65 + REACH SVHC / ECHA SCIP (> 0.1% w/w).
- NIST metrological-traceability policy; ISO/IEC 17025; Sensirion SHT4x per-unit accredited cal (SCS 0158) + datasheet; DS18B20 datasheet; Onset ~$140 3-point cost.
- CDC/VFC DDL requirements + NIST IR 8457; FDA 21 CFR Part 11 / EU Annex 11 / GAMP 5; FDA Food Code 2022 / EC 852/2004; EN 12830:2018 / EN 13485:2023 (+ EN 13486).
- ASHRAE TC 9.9 (data centers) & museum guidance; cannabis/greenhouse VPD agronomy; procurement norms (CGL insurance, W-9); channel taxonomy (direct/MSP/VAR/SI/distributor).
