# Setpoint — Unit Label Template

What goes on the physical label applied to every Setpoint during QC
(step 8 of [QC_CHECKLIST.md](QC_CHECKLIST.md)). The identity values are captured
by [`firmware/factory_flash.py`](../firmware/factory_flash.py) from the firmware's
boot **`[label]` serial line** — they are derived from the DS18B20 sensor ROM and
**persisted in NVS**, so they are read off the running firmware, **not** computed
from the MAC ([`firmware/src/protocol.h`](../firmware/src/protocol.h) is the
identity source of truth).

The label is the customer's only reference for setup, so it MUST be correct and
legible. A non-technical buyer uses it to (a) find the setup Wi-Fi and (b) scan a
QR to the setup page.

> **Two different labels.** A **DIY kit** is a bag of components, not a finished
> product, so it carries only the identity fields below — no FCC block. An
> **assembled unit** is a finished product and legally may not ship without the
> regulatory block in the next section. Do not mix them up: an assembled unit
> missing the FCC text cannot lawfully be sold, and a kit carrying it is claiming
> an authorisation that does not cover a bag of parts.

---

## Regulatory block — ASSEMBLED UNITS ONLY

Required on every assembled unit before sale, and **not valid until the Part 15B
SDoC test report is signed** ([`COMPLIANCE.md`](COMPLIANCE.md)). Three parts, all
mandatory:

**1. Module identification** — 47 CFR §15.19, the host carries the module's grant:

```
Contains FCC ID: 2AC7Z-ESPC3WROOM02
```

> ⛔ **VERIFY THIS STRING BEFORE THE FIRST LABEL IS PRINTED.** It must be the FCC ID of the
> *exact* module variant soldered to the board. The board carries an **`ESP32-C3-WROOM-02`**
> (confirmed from `hardware/rev2/` — `U1`, `RF_Module:ESP32-C3-WROOM-02`), and the ID above is
> the expected one for it, but it has not been checked against Espressif's certificate from
> inside this repo.
>
> Check it against the module datasheet or Espressif's certification page, and mind the
> variants — a `-WROOM-02U` (external antenna) is a **different grant** from a `-WROOM-02`.
>
> Every doc here said `2AC7Z-ESPC3MINI1` until 2026-08-04, because the rev-2 *plan*
> (`PCB_REV2_MODULE.md`) specified an `ESP32-C3-MINI-1` and the board was built with a
> WROOM-02 instead. Printing a module's FCC ID on a product that does not contain that module
> is a false statement of conformity, so this is the one string on the label worth checking
> twice.

**2. Compliance statement** — §15.19(a)(3), reproduce verbatim:

```
This device complies with part 15 of the FCC Rules. Operation is subject to
the following two conditions: (1) This device may not cause harmful
interference, and (2) this device must accept any interference received,
including interference that may cause undesired operation.
```

**3. Responsible party** — §2.1077(a)(3). The SDoC names a US-located entity, and
this must match the SDoC, the warranty, the insurance policy and the W-9
**character for character**:

```
Datum Laboratories LLC
1304 Cottonwood Court Northwest, Kennesaw, GA 30152, USA
support@datumlaboratories.com
```

**Model number** — assign one per version and keep it stable; it identifies the
unit the SDoC covers:

| Version | Model number |
|---|---|
| Setpoint Portable (battery) | `SETPOINT-P-C3` |
| Setpoint Fixed (USB) | `SETPOINT-F-C3` |
| DIY kit (no FCC block) | `SETPOINT-DIY-C3` |

**If the enclosure is too small for the full text**, FCC KDB 784748 permits an
**e-label** or placement in the user manual — but the "Contains FCC ID" line and
the responsible party should stay physically on the unit wherever possible, and
the manual must then carry the §15.19(a)(3) statement. Decide this **before** the
SDoC, because the lab tests the product as it ships.

---

## Fields on each label

| # | Field | Value / format | Source |
|---|-------|----------------|--------|
| 1 | **Probe ID** (human-readable) | `Setpoint-<HEX6>` — 6 UPPERCASE hex from the DS18B20 sensor ROM (MAC fallback), persisted in NVS. e.g. `Setpoint-9A3F2C` | `[label]` line `probe_id=` |
| 2 | **Setup Wi-Fi (SSID)** | `Setpoint-<HEX6>` (same string as Probe ID); **open** (no password) | `[label]` line `ap_ssid=` |
| 3 | **Setup QR** | QR encoding the setup page URL (see below) | printed |
| 4 | **mDNS host** (optional, small print) | `Setpoint-<HEX6>.local` (== Probe ID) | derived from Probe ID |

Notes:
- Fields 1–2 both come from the same `[label]` serial line the firmware prints on
  every boot; capture them together and do **not** hand-edit one without the other.
- The current firmware (**v2.8.2**) has **no** provision secret — `POST /provision`
  is accepted on the trusted LAN. The setup network is an **open** SoftAP (no
  password), present only during first-time setup, so there is nothing secret to print.
- The **setup QR** should point at the customer setup entry point, e.g.
  `http://192.168.4.1` (the captive portal, reachable once the phone joins the
  probe's SoftAP), or your hosted setup-help page for this product. Keep it
  consistent across a batch.

---

## Printable label layout sketch

Small 2-up thermal/laser label, roughly 50 × 25 mm. Adjust to your stock.

**DIY kit** — identity only, no regulatory block:

```
+------------------------------------------------------+
|  Setpoint  •  Datum Labs              [ ##### ]      |
|                                       [ #QR# ]  <- scan to set up
|  ID:   Setpoint-9A3F2C                [ ##### ]      |
|                                                      |
|  Setup Wi-Fi : Setpoint-9A3F2C   (open)              |
|  host: Setpoint-9A3F2C.local                         |
+------------------------------------------------------+
   fw 2.8.2 / proto 1        S/N: __________  QC:____
```

**Assembled unit** — the same identity fields plus the regulatory block. A
larger label (or a second one on the underside) is usually needed:

```
+------------------------------------------------------+
|  Setpoint  •  Datum Labs              [ ##### ]      |
|  Model: SETPOINT-P-C3                 [ #QR# ]       |
|  ID:   Setpoint-9A3F2C                [ ##### ]      |
|  Setup Wi-Fi : Setpoint-9A3F2C   (open)              |
+------------------------------------------------------+
|  Contains FCC ID: 2AC7Z-ESPC3WROOM02                   |
|  This device complies with part 15 of the FCC Rules. |
|  Operation is subject to the following two           |
|  conditions: (1) This device may not cause harmful   |
|  interference, and (2) this device must accept any   |
|  interference received, including interference that  |
|  may cause undesired operation.                      |
|  Datum Laboratories LLC, Kennesaw, GA, USA           |
+------------------------------------------------------+
   fw 2.8.2 / proto 1        S/N: __________  QC:____
```

- Top-right: the setup **QR** (field 3).
- Big, unambiguous type for the Wi-Fi SSID (field 2) — this is what a
  non-technical buyer squints at. The setup network is **open**, so there is no
  password to print.
- `S/N` and `QC` blanks are hand-filled at boxing (serial + operator initials)
  and mirror the serial-log CSV row.

---

## Serial-log CSV column spec (one row per unit)

The maker fills **one row per unit** during QC and keeps the file as the batch
build/traceability record. This is a manufacturing log — it is **separate** from
the hub's telemetry CSV (`timestamp,temperature_c,temperature_f,probe_id,`
`humidity_pct,vpd_kpa`); do not conflate them.

Header row:

```
serial,build_date,operator,mac,probe_id,ap_ssid,fw_version,version,test_wifi_ssid,temperature_c,ice_c,ingest_ok,qc_result,notes
```

| Column | Meaning | Example |
|--------|---------|---------|
| `serial` | Your batch serial / sequence for the unit | `TP2607-001` |
| `build_date` | Date built (ISO) | `2026-07-06` |
| `operator` | Who ran QC (initials) | `TJ` |
| `mac` | Full chip MAC from esptool (log/traceability only) | `A4:CF:12:9A:3F:2C` |
| `probe_id` | `Setpoint-<HEX6>` from the `[label]` line (must be unique in file) | `Setpoint-9A3F2C` |
| `ap_ssid` | SoftAP SSID (== probe_id); the AP is **open** | `Setpoint-9A3F2C` |
| `fw_version` | Flashed firmware version | `2.8.2` |
| `version` | Product version built ([VERSIONS.md](VERSIONS.md)) — `Portable` or `Fixed` | `Portable` |
| `test_wifi_ssid` | Bench Wi-Fi the unit joined in QC | `bench-2g` |
| `temperature_c` | Plausible `last_c` observed at QC | `23.4` |
| `ice_c` | Ice-bath 0 °C check (QC step 5.3); must be `0 ± 0.5` | `0.1` |
| `ingest_ok` | Bench hub ingest confirmed (fresh CSV row for this probe_id) | `yes` |
| `qc_result` | Overall gate result | `PASS` |
| `notes` | Failed-step number / rework / anything | `—` |

Example rows:

```
serial,build_date,operator,mac,probe_id,ap_ssid,fw_version,version,test_wifi_ssid,temperature_c,ice_c,ingest_ok,qc_result,notes
TP2607-001,2026-07-06,TJ,A4:CF:12:9A:3F:2C,Setpoint-9A3F2C,Setpoint-9A3F2C,2.8.2,Portable,bench-2g,23.4,0.1,yes,PASS,plug-and-play
TP2607-002,2026-07-06,TJ,A4:CF:12:7B:10:44,Setpoint-7B1044,Setpoint-7B1044,2.8.2,Fixed,bench-2g,22.9,-0.1,yes,PASS,plug-and-play
```
