# Setpoint ⇄ Setpoint Protocol

**Protocol version: `proto = 1`**
Product: **Setpoint** (hub) / **Setpoint** (probe) · Software version: `2.0.0`

This is the authoritative, versioned contract between Setpoint firmware and the
Setpoint appliance. It is the single source of truth for the wire format: identity,
discovery, provisioning, and ingest. Firmware and hub MUST both conform to this
document. Where this file and code disagree, that is a bug in one of them — fix it,
don't silently diverge.

Setpoint is a **local-first, no-cloud** appliance. All traffic in this document is
LAN-only (probe ⇄ hub, same subnet). There is no outbound telemetry and no account.

---

## 1. Terminology & versioning

| Term | Meaning |
|------|---------|
| **Hub** | Setpoint — Python/Flask+Dash app served by waitress on TCP **8088**. |
| **Probe** | Setpoint — ESP32 firmware, HTTP server on TCP **80**. |
| **`proto`** | Integer protocol version. This document defines `proto = 1`. |
| **Device token** | One shared secret per hub. Authenticates mutating hub endpoints **and** is provisioned onto probes, which echo it back as `X-Token`. |
| **Provision secret** | Per-unit secret printed on the probe's label/QR. Guards the probe's `/provision` endpoint. Distinct from the device token. |

**Compatibility rule:** the hub **warns, it does not crash**, on an unknown or
mismatched `proto`. A probe advertising `proto` other than `1` is still listed and
its data still ingested on a best-effort basis; the hub logs a warning so the
mismatch is diagnosable. Firmware must therefore never assume a hub will reject it
purely for a version skew. Breaking wire changes require bumping `proto` to `2` and a
new revision of this document.

---

## 2. Probe identity

The probe identity is derived once, deterministically, from silicon and is the single
source of truth used everywhere (mDNS TXT, HTTP headers, `/whoami`).

```
suffix    = last 3 bytes of the ESP32 eFuse (base) MAC, uppercase hex (6 chars)
probe_id  = "Setpoint-" + suffix          e.g.  Setpoint-9A3F2C
hostname  = probe_id + ".local."          e.g.  Setpoint-9A3F2C.local.
```

- `probe_id` is stable for the life of the hardware.
- `probe_id` MUST match `^[A-Za-z0-9_-]{1,32}$` (the hub rejects anything else — see §6).
- The **same** `probe_id` string appears in the mDNS TXT `id` key, in the
  `X-Probe-ID` ingest header, and in `/whoami`. These MUST be byte-for-byte equal.

---

## 3. mDNS discovery

The probe **advertises**; the hub **browses** (zeroconf).

| Field | Value |
|-------|-------|
| Service type | `_temps-probe._tcp.local.` |
| Transport / port | TCP **80** |
| Server (host) | `Setpoint-<HEX6>.local.` (== `probe_id`, verbatim) |

### TXT record keys

| Key | Value | Notes |
|-----|-------|-------|
| `id` | `<probe_id>` | e.g. `Setpoint-9A3F2C`. **Invariant:** this MUST equal the `X-Probe-ID` header the probe later sends on ingest. |
| `name` | friendly name, else `<probe_id>` | Human label; falls back to `probe_id`. |
| `fw` | firmware semver | e.g. `2.0.0`. |
| `proto` | `1` | Protocol version this firmware speaks. |

**`id == X-Probe-ID` invariant.** The hub keys and reconciles probes on this equality.
On ingest, if both the `X-Probe-ID` header and a body `probe_id` are present and they
disagree, the hub logs a warning (`probe_id mismatch: header=… body=…`) and proceeds
using the header value — it does not reject the reading.

> The hub also advertises *itself* over mDNS as an `_http._tcp.local.` service so a
> browser can find the dashboard. That is a convenience for humans and is **not** part
> of this probe protocol; probes never need to browse for the hub — they are told the
> ingest URL during provisioning (§5).

---

## 4. Probe HTTP endpoints (firmware serves, port 80)

### 4.1 `POST /provision`

Configures the probe with the hub's ingest URL, the device token, and the post
interval. Persisted to NVS so it survives reboots.

**Request headers**

| Header | Required | Value |
|--------|----------|-------|
| `Content-Type` | yes | `application/json` |
| `X-Provision-Secret` | **yes** | Per-unit provision secret from the label/QR. The probe MUST reject `/provision` without a valid secret (`401`). |

**Request body**

```json
{
  "server_url": "http://192.168.1.50:8088/api/ingest",
  "token": "s3cr3t-device-token",
  "interval_ms": 5000,
  "resolution_bits": 11
}
```

- `resolution_bits` is **optional** (DS18B20 resolution, `9`..`12`; 9=0.5 °C/~94 ms,
  10=0.25 °C, 11=0.125 °C/~375 ms default, 12=0.0625 °C/~750 ms). Omitting it leaves
  the probe's current resolution unchanged, so a hub that doesn't manage it (or an
  older one) is unaffected; an older probe simply ignores the unknown field. Note
  that 12-bit's 750 ms conversion exceeds a 500 ms interval and caps the sample rate.

**Response** `200 OK`

```json
{ "id": "Setpoint-9A3F2C", "name": "Garage Fridge", "fw": "2.0.0", "accepted": true }
```

The probe persists `server_url`, `token`, `interval_ms`, and `resolution_bits` to NVS
and begins posting (§5). It echoes `resolution_bits` in `/whoami` and `/status` so the
hub can confirm the applied value.

> **Hub implementation note.** Setpoint's built-in auto-provisioner and the
> `POST /api/provision` endpoint push `{server_url, token, interval_ms, resolution_bits}`
> to the probe's `/provision` (trying the probe IP first, then its `.local` hostname).
> The `X-Provision-Secret` is a per-unit secret held by the operator; supply it via
> the provisioning caller for units that enforce it.

### 4.2 `GET /whoami`

```json
{ "id": "Setpoint-9A3F2C", "name": "Garage Fridge", "fw": "2.0.0", "mac": "24:6F:28:9A:3F:2C" }
```

`id` MUST equal the mDNS TXT `id` and the `X-Probe-ID` ingest header.

### 4.3 `GET /status`

```json
{
  "id": "Setpoint-9A3F2C",
  "wifi_rssi": -57,
  "uptime_s": 43120,
  "last_post_ok": true,
  "last_post_code": 200,
  "server_url": "http://192.168.1.50:8088/api/ingest",
  "temperature_c": 4.2,
  "sensor_ok": true
}
```

`sensor_ok` is `false` when the sensor reports a fault (see §8); in that state the
probe skips posting.

On the humidity build variant (firmware built with `-D SENSOR_SHT4x`, see §8) the
response carries one extra field, `humidity_pct` (0–100):

```json
{ "…": "…", "temperature_c": 24.1, "humidity_pct": 58.3, "sensor_ok": true }
```

Temperature-only builds (DS18B20 / MAX31855) omit `humidity_pct` entirely.

---

## 5. Ingest — probe → hub

Every `interval_ms`, the probe POSTs the latest good reading to the provisioned
`server_url` (which is the hub's `POST /api/ingest`).

**Request headers**

| Header | Required | Value |
|--------|----------|-------|
| `Content-Type` | yes | `application/json` |
| `X-Probe-ID` | yes | `<probe_id>` — MUST equal the mDNS TXT `id`. |
| `X-Token` | yes* | The device token received during provisioning. *Required whenever the hub has a token set (the shipped product always does — see §7). |

**Request body**

```json
{
  "temperature_c": 4.2,
  "probe_id": "Setpoint-9A3F2C",
  "timestamp": "2026-07-06T14:03:11"
}
```

- Send **`temperature_c`** (preferred) **or** `temperature_f`; the hub derives the
  other. (For robustness the hub also accepts the aliases `temp_c`/`t_c`/`c` and
  `temp_f`/`t_f`/`f`, but firmware SHOULD emit `temperature_c`.)
- `probe_id` in the body is optional but SHOULD be sent and MUST match `X-Probe-ID`.
- `timestamp` is optional ISO-8601, and **may carry millisecond precision**
  (`2026-07-06T14:03:11.500Z`), which the hub preserves so a high-rate cadence
  (down to the 500 ms floor) stays distinguishable instead of collapsing onto one
  whole-second stamp. The hub holds the authoritative clock, so if the field is
  omitted **or not a valid ISO datetime** the hub stamps its own receipt time. A
  probe with a synced clock (NTP, or an RTC restored across deep sleep) SHOULD
  send it — the current firmware does, to ms precision. (Alias `ts` also accepted.)
- **`humidity_pct`** is **optional** (0–100 %RH). Only the SHT4x build variant emits
  it; temperature-only probes omit it. The hub validates it (finite, 0–100) and
  silently ignores anything invalid. (Aliases `humidity`/`rh`/`h` also accepted.)
  A reading *with* humidity looks like:

```json
{
  "temperature_c": 24.1,
  "humidity_pct": 58.3,
  "probe_id": "Setpoint-9A3F2C",
  "timestamp": "2026-07-06T14:03:11"
}
```

- **`battery_pct`** is **optional** (0–100 %): a battery-powered probe MAY report its
  remaining charge. Mains-powered probes simply omit it.
- **`battery_v`** is **optional** (volts): as an alternative to `battery_pct`, a probe
  may report its raw single-cell LiPo pack voltage and let the hub do the conversion —
  the hub maps it linearly **3.0 V → 0 %, 4.2 V → 100 %** and clamps to that range. A
  voltage outside the plausible cell band (2.5–5.0 V) is sensor junk, not a nearly
  full/empty cell, and is treated as "no battery reading". When `battery_pct` is
  present it takes precedence and `battery_v` is not consulted.
- Both battery fields are **ignored when absent or invalid** — like humidity, battery
  is never a reason to reject a good temperature (see §6). The derived percentage is
  stored per reading and surfaced in the hub UI and readings API; adding these
  backward-compatible optional fields required **no `proto` change**.

#### Humidity & VPD

The probe only ever reports **temperature** and (on the SHT4x variant) **humidity**.
**VPD (vapour pressure deficit) is not part of the wire protocol** — the probe never
sends it. The **hub computes VPD** from the temperature + humidity of each reading
using the **Tetens** saturation-vapour-pressure formula, optionally applying a
leaf-temperature offset from hub config `settings.vpd_leaf_offset_c` (default `0.0`;
growers commonly use `~2.0` to model leaf-below-air temperature). VPD is derived,
stored, and displayed entirely hub-side, so adding it required **no `proto` change**:
`humidity_pct` is a backward-compatible optional field and this document remains
`proto = 1`.

**Success** `200 OK`

```json
{ "ok": true }
```

**Errors**

| Status | Body | Cause |
|--------|------|-------|
| `400` | `{"ok": false, "error": "<reason>"}` | No temperature value, non-finite, or out of range (§6). |
| `401` | `{"ok": false, "error": "unauthorized"}` | Missing/wrong token when the hub requires one. |
| `413` | `{"ok": false, "error": "payload too large"}` | Body exceeds 64 KiB. |
| `405` | `{"ok": false, "error": "method not allowed; use POST"}` | `GET /api/ingest` — ingest is **POST-only**. |
| `500` | `{"ok": false, "error": "<reason>"}` | Persist failure on the hub. |

---

## 6. Hub validation rules (`POST /api/ingest`)

The hub validates every reading before it touches the log:

1. **Temperature present:** at least one of the celsius/fahrenheit keys must be
   present and non-empty, else `400`.
2. **Finite:** the resolved celsius value must be a finite number (no `NaN`/`inf`),
   else `400`.
3. **Range:** celsius must satisfy `-60.0 ≤ t_c ≤ 150.0`, else `400`. This band
   rejects sensor fault codes (e.g. `85.0` power-on, `-127` disconnected) so they
   cannot poison dashboard statistics or the auto-scaled axis.
4. **probe_id:** sanitized against `^[A-Za-z0-9_-]{1,32}$`. A value that fails the
   regex is dropped to empty string (the reading is still logged, without an id).
5. **Method:** `GET /api/ingest` returns `405`; only `POST` mutates the log. (A prior
   version accepted `GET`, letting a drive-by `<img>` poison the CSV — closed.)
6. **Size:** bodies over **64 KiB** are rejected `413`.
7. **Humidity (optional):** if `humidity_pct` is present it must be finite and within
   `0 ≤ rh ≤ 100`, else it is dropped (the reading is still accepted — humidity is
   never a reason to reject a good temperature). When a valid humidity is present the
   hub derives **VPD** from it (see §5, *Humidity & VPD*).
8. **Battery (optional):** if `battery_pct` is present it must be finite and within
   `0 ≤ pct ≤ 100`, else it is dropped. Failing that, a present `battery_v` must be
   finite and within `2.5 ≤ v ≤ 5.0`; it is mapped linearly `3.0 V → 0 %`,
   `4.2 V → 100 %` and clamped. An absent or invalid battery value never rejects the
   reading (see §5).

Accepted readings are persisted to the CSV log with columns:

```
timestamp,temperature_c,temperature_f,humidity_pct,vpd_kpa,probe_id
```

`humidity_pct` and `vpd_kpa` are blank for temperature-only probes; older logs are
auto-upgraded to this header on load. Per-probe calibration (`gain` then `offset_c`,
from hub config) is applied to temperature before logging, and fahrenheit is recomputed
from the calibrated celsius.

---

## 7. Token flow (single device token)

There is exactly **one** device token per hub. It authenticates mutating hub endpoints
and is the value probes echo on ingest.

```
        ┌── SERVER_TOKEN env  ─┐
        │   config token       │   (precedence, first non-empty wins)
        │   freshly generated  │   (secrets.token_urlsafe; saved to config.json)
        └──────────┬───────────┘
                   │  held in hub config as  provision_token
                   ▼
   hub  ──POST /provision {server_url, token, interval_ms}──►  probe   (token persisted to NVS)
                   ▲                                                │
                   │                                                │  every interval_ms
                   └──────  POST /api/ingest  X-Token: <token> ◄────┘
```

- **Resolution order at startup:** `SERVER_TOKEN` env → existing config
  `provision_token` → freshly generated (persisted to `config.json`, printed
  once at startup). The shipped product therefore always has a non-empty token and is
  **secure-by-default** while remaining plug-and-play, because the same token is pushed
  to every discovered probe by the auto-provisioner.
- **How the hub reads a token on a request:** `X-Token` header → `?token=` query param
  → JSON body `token` field, compared for equality against the device token.
- **Empty token = open mode.** If the token is empty (tests / air-gapped dev) the hub
  accepts unauthenticated requests. The shipped appliance never runs this way.
- The token is a secret: `GET /api/config` redacts it (and `smtp_password`) to
  `"***set***"`. It is never written to the downloadable CSV.

### Hub REST endpoints (prefix `/api`)

| Endpoint | Auth | Purpose |
|----------|------|---------|
| `GET /api/health` | none | `{ok, version, protocol, probes, base, time, rows_written, ingest_rejected, write_failures, last_write_age_sec, healthy}` |
| `GET /api/config` | token | Redacted config. |
| `POST /api/config` | token | Update config. |
| `GET /api/probes` | none | `[{host, ip, port, name, probe_id, last_seen}]` |
| `POST /api/provision` | token | Hub pushes ingest URL + token to probe `/provision`. |
| `POST /api/ingest` | token | Ingest one reading (§5, §6). |
| `GET  /api/ingest` | — | `405`, POST-only. |
| `POST /api/ingest_csv` | token | Bulk ingest (≤ 1000 rows/request). |

`GET /download/temperature_log.csv` is the **only** downloadable file.

---

## 8. Sensor faults

Sensor: **DS18B20** on a GPIO with a 4.7 kΩ pull-up (thermocouple **MAX31855** or
temp+humidity **SHT4x** optional at build time — see firmware `build_flags`
`-D SENSOR_MAX31855` / `-D SENSOR_SHT4x`). Known fault readings — `85.0 °C` (power-on
default), `-127 °C` / `NaN` (disconnected) — MUST cause the probe to set
`sensor_ok = false` and **skip posting** that cycle. As defense in depth, any such
value that did reach the hub is rejected by the range/finite checks in §6.

---

## 9. SoftAP setup flow

A probe with no saved Wi-Fi credentials brings up onboarding:

1. Probe starts an **open SoftAP** (no password) with SSID `Setpoint-<hex>`.
2. The operator joins that AP; a **captive portal** at `http://192.168.4.1` lists
   nearby networks.
3. Operator selects the home SSID and enters its password; the probe **persists the
   credentials to NVS**, leaves AP mode, and joins the home network.
4. On the home network the probe advertises over mDNS (§3) and awaits provisioning
   (§5). No cloud, no account — configuration never leaves the LAN.

---

## 10. Threat model (LAN-scoped)

Setpoint is designed for a trusted home/small-business LAN, not a hostile network. The
protocol nonetheless hardens against realistic local threats:

| Threat | Mitigation |
|--------|-----------|
| Rogue host poisoning the log | Mutating endpoints require the device token (`X-Token`); ingest is POST-only, so a drive-by `GET`/`<img>` cannot write. |
| Sensor faults / bad data corrupting stats | Finite + `-60..150 °C` range validation (§6); firmware also suppresses fault codes at source (§8). |
| Disk-fill / DoS | 64 KiB body cap (`413`); bulk CSV capped at 1000 rows/request. |
| Unauthorized probe reconfiguration | Probe `/provision` requires the per-unit `X-Provision-Secret` from the label. |
| Spreadsheet formula injection via CSV export | Fields beginning with `= + - @` etc. are neutralized on write. |
| Secret leakage | Token and SMTP password redacted in `GET /api/config`; the token is never in the CSV; the download route serves **only** `temperature_log.csv`. |
| Identity spoofing / mix-ups | Deterministic MAC-derived `probe_id`; `id == X-Probe-ID` invariant reconciled at the hub. |

**Out of scope for `proto = 1`:** transport encryption (plain HTTP on the LAN),
per-probe mutual auth beyond the shared device token, and defense against an attacker
who already controls the local network. These are documented limits, not oversights,
for a local-first appliance.

---

*This document defines `proto = 1`. Any incompatible change bumps the version and this
file is revised alongside it.*
