# TempSensor — Unit Label Template

What goes on the physical label applied to every TempSensor during QC
(step 8 of [QC_CHECKLIST.md](QC_CHECKLIST.md)). The identity values are captured
by [`firmware/factory_flash.py`](../firmware/factory_flash.py) from the firmware's
boot **`[label]` serial line** — they are derived from the DS18B20 sensor ROM and
**persisted in NVS**, so they are read off the running firmware, **not** computed
from the MAC ([`firmware/src/protocol.h`](../firmware/src/protocol.h) is the
identity source of truth).

The label is the customer's only reference for setup, so it MUST be correct and
legible. A non-technical buyer uses it to (a) find the setup Wi-Fi and (b) scan a
QR to the setup page.

---

## Fields on each label

| # | Field | Value / format | Source |
|---|-------|----------------|--------|
| 1 | **Probe ID** (human-readable) | `TempSensor-<HEX6>` — 6 UPPERCASE hex from the DS18B20 sensor ROM (MAC fallback), persisted in NVS. e.g. `TempSensor-9A3F2C` | `[label]` line `probe_id=` |
| 2 | **Setup Wi-Fi (SSID)** | `TempSensor-<HEX6>` (same string as Probe ID); **open** (no password) | `[label]` line `ap_ssid=` |
| 3 | **Setup QR** | QR encoding the setup page URL (see below) | printed |
| 4 | **mDNS host** (optional, small print) | `TempSensor-<HEX6>.local` (== Probe ID) | derived from Probe ID |

Notes:
- Fields 1–2 both come from the same `[label]` serial line the firmware prints on
  every boot; capture them together and do **not** hand-edit one without the other.
- The current firmware (**v2.4.0**) has **no** provision secret — `POST /provision`
  is accepted on the trusted LAN. The setup network is an **open** SoftAP (no
  password), present only during first-time setup, so there is nothing secret to print.
- The **setup QR** should point at the customer setup entry point, e.g.
  `http://192.168.4.1` (the captive portal, reachable once the phone joins the
  probe's SoftAP), or your hosted setup-help page for this product. Keep it
  consistent across a batch.

---

## Printable label layout sketch

Small 2-up thermal/laser label, roughly 50 × 25 mm. Adjust to your stock.

```
+------------------------------------------------------+
|  TempSensor  •  TempSensor            [ ##### ]       |
|                                       [ #QR# ]  <- scan to set up
|  ID:   TempSensor-9A3F2C             [ ##### ]       |
|                                                      |
|  Setup Wi-Fi : TempSensor-9A3F2C   (open)           |
|  host: TempSensor-9A3F2C.local                      |
+------------------------------------------------------+
   fw 2.4.0 / proto 1        S/N: __________  QC:____
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
serial,build_date,operator,mac,probe_id,ap_ssid,fw_version,test_wifi_ssid,temperature_c,ingest_ok,qc_result,notes
```

| Column | Meaning | Example |
|--------|---------|---------|
| `serial` | Your batch serial / sequence for the unit | `TP2607-001` |
| `build_date` | Date built (ISO) | `2026-07-06` |
| `operator` | Who ran QC (initials) | `TJ` |
| `mac` | Full chip MAC from esptool (log/traceability only) | `A4:CF:12:9A:3F:2C` |
| `probe_id` | `TempSensor-<HEX6>` from the `[label]` line (must be unique in file) | `TempSensor-9A3F2C` |
| `ap_ssid` | SoftAP SSID (== probe_id); the AP is **open** | `TempSensor-9A3F2C` |
| `fw_version` | Flashed firmware version | `2.4.0` |
| `test_wifi_ssid` | Bench Wi-Fi the unit joined in QC | `bench-2g` |
| `temperature_c` | Plausible `last_c` observed at QC | `23.4` |
| `ingest_ok` | Bench hub ingest confirmed (fresh CSV row for this probe_id) | `yes` |
| `qc_result` | Overall gate result | `PASS` |
| `notes` | Failed-step number / rework / anything | `—` |

Example rows:

```
serial,build_date,operator,mac,probe_id,ap_ssid,fw_version,test_wifi_ssid,temperature_c,ingest_ok,qc_result,notes
TP2607-001,2026-07-06,TJ,A4:CF:12:9A:3F:2C,TempSensor-9A3F2C,TempSensor-9A3F2C,2.4.0,bench-2g,23.4,yes,PASS,plug-and-play
TP2607-002,2026-07-06,TJ,A4:CF:12:7B:10:44,TempSensor-7B1044,TempSensor-7B1044,2.4.0,bench-2g,22.9,yes,PASS,plug-and-play
```
