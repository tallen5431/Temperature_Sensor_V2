# Tindie Listing — Setpoint (ready to paste)

> _**Maker note (delete before publishing):** this maps the copy in [`LISTING.md`](LISTING.md) onto
> Tindie's actual listing fields so you can paste section-by-section. The brand is set — product
> **Setpoint**, store/company **Datum Labs**. Set your real **price**, **photos**, and **support
> link** first. See the "Before you publish" checklist at the
> bottom — the two blockers are **photos of a real unit** and (for the assembled option) **FCC**._

Tindie listing fields, in order:

---

## 1. Product name

```
Setpoint — Local Wi-Fi Temperature Monitor for Homelabs & Server Rooms (No Cloud · Prometheus / Home Assistant)
```

## 2. Summary (one line, keep it under ~140 chars)

```
Wi-Fi temp sensor that reports to a free app on YOUR own PC — no cloud, no account. Prometheus, Home Assistant & MQTT ready.
```

## 3. Category & tags

- **Category:** Electronics → Sensors (or "Internet of Things").
- **Tags** (for search — use as many as apply): `esp32`, `temperature`, `sensor`, `wifi`,
  `homelab`, `home-assistant`, `mqtt`, `prometheus`, `grafana`, `self-hosted`, `no-cloud`,
  `ds18b20`, `server-room`, `iot`.

## 4. Price & options

The **hub software is free**; the probe is the paid item. Set the price you can sustain (your BOM is
~$22/unit, ~$16–18 at qty 10+ — target ~50–55% gross margin). Suggested starting points:

| Option (Tindie "product option") | What it is | Suggested price |
|---|---|---|
| **DIY Kit** | Bag of parts + label/QR to the browser-flash page; buyer assembles & flashes | **~$39** |
| **Assembled & Tested** | Pre-built, pre-flashed, QC'd unit (needs FCC SDoC — see below) | **~$69** |
| **4-Probe Pack (Assembled)** | Four units for a whole rack/closet | **~$189** |

> Start with the **DIY Kit** option only if you haven't cleared FCC yet — kits sidestep the
> finished-product rules and get you live fastest. Add the Assembled options once your SDoC is done.

## 5. Description (Tindie supports Markdown — paste this)

```markdown
**Know the instant your rack, closet, or NAS gets too hot — without handing your data to somebody
else's cloud.** Setpoint reports to a small, free app you run on **your own** PC, mini-PC, or NAS,
so your readings never leave the building and your alerts keep working even when the internet doesn't.

### Why it's different
- 🔒 **It can't be shut down.** The probe reports to a hub app you run yourself, and the firmware is
  open. No vendor account to close, no server to sunset — cloud thermometers have bricked overnight
  when their servers went dark. This one won't.
- 🏠 **Your data stays on-prem.** Readings live in a local SQLite database on your machine, exportable
  to CSV anytime. No account, no telemetry, nothing phoning home.
- 🧩 **Drops into the stack you already run:** Prometheus `/metrics`, Home Assistant + MQTT
  auto-discovery, Docker/headless on a NAS, one-click CSV export.
- 🌡️ **One hub, many probes.** Add probes and they self-discover on your LAN — pay for sensors, not a
  per-sensor gateway.
- 🛎️ **Alerts that reach you.** Per-probe high/low thresholds → email or webhook, evaluated on the hub
  so they fire even with no dashboard open.

### Honest specs
| Spec | Setpoint |
|---|---|
| Sensor | Maxim **DS18B20**, waterproof stainless probe (1 m lead) |
| Accuracy | **±0.5 °C typical, uncalibrated** (add a per-probe offset in the app). Resolution 0.0625 °C is *not* accuracy. |
| Connectivity | **2.4 GHz** Wi-Fi (no 5 GHz) |
| Power | USB 5 V, always-on (a battery/deep-sleep build is available on request) |
| Probes per hub | Dozens — one hub covers a whole rack/site |
| Data | Local SQLite on your PC, one-click CSV export |
| Hub software | **Free.** Windows 10/11 or Linux; runs headless / in Docker |
| Integrations | Prometheus, MQTT + Home Assistant, CSV, email/webhook alerts |
| Firmware | Open source; on-device Wi-Fi setup |

> **Needs an always-on computer** (PC, mini-PC, NAS, or home server) on the same network to run the
> free hub. If you don't already leave a machine on 24/7, this isn't the right pick.

### What's in the box
- 1× Setpoint (ESP32 + waterproof DS18B20 in an enclosure) — *DIY Kit ships as parts to assemble*
- 1× USB cable
- Quick-start card + link to the full user manual
- Unit label: serial ID, **open** setup Wi-Fi name (no password), setup QR

*(The hub app is a free download — no disc, no account.)*

### FAQ
- **Needs internet/an account?** No — LAN only. Internet is only used if you want email alerts to leave your network.
- **Accuracy?** ±0.5 °C typical, uncalibrated — great for "is my rack within range and trending safe." Not a certified/NIST/medical instrument.
- **Wi-Fi?** 2.4 GHz only. Setup is on-device (join the probe's temporary network, pick yours) — no phone app.
- **Power loss?** Local alerts keep firing during a *WAN* outage, but nothing survives a full power loss — put your router/hub on a UPS if that's your risk.
- **Open firmware?** Yes — read it, build it, reflash it. You're never locked in.
```

## 6. Shipping

- Set a **shipping profile**: ship-from country, destinations (start **domestic-only** to keep it
  simple, add international later), and a flat rate per option (the 4-pack weighs more).
- Set a realistic **handling time** (e.g. 3–5 business days for a hand-built batch).

## 7. Photos (upload in this order — first image is the thumbnail)

1. **Hero** — unit on a clean dark surface, probe lead coiled.
2. **In context** — probe tip inside an open server rack, unit velcro'd to a rail.
3. **Dashboard screenshot** — live web dashboard with a chart + gauge.
4. **Integration screenshot** — the probe in **Grafana** or Home Assistant.
5. **Scale shot** — unit in hand.
6. **Macro** — the stainless waterproof probe tip.
7. **Multi-probe** — 3–4 units (sells the 4-pack).
8. **What's-in-the-box flat-lay** — unit, cable, quick-start card, label/QR.
9. **Label close-up** — serial ID + setup QR (signals traceability).

> A short **setup GIF/video** (join probe Wi-Fi → pick network → it appears on the dashboard) converts
> well if Tindie's media supports it.

---

## Before you publish — checklist

- [ ] **Real photos of a real unit** — Tindie listings live or die on photos. This requires a
      **hand-built + QC'd unit** (`docs/QC_CHECKLIST.md`), the same batch step that's your #1 to-do.
- [ ] **Support link** swapped in (replace `example.com/support`). Brand is **Setpoint, by Datum Labs** — Tindie store name = **Datum Labs**.
- [ ] **Prices** set from your real costs (`docs/BOM.md`).
- [ ] **Inventory count** from your first batch.
- [ ] **Payout set up** — Tindie revamped payouts in mid-2026; confirm the current method at signup.
- [ ] **Exclusivity:** a product active on Tindie **can't be listed elsewhere on the web** at the same
      time. Use Tindie as your one paid channel for the probe; keep your own site for the *free
      software*, waitlist, and build-in-public — not a competing listing of the same SKU.
- [ ] **FCC:** the **DIY Kit** option sidesteps finished-product rules and can go live now; the
      **Assembled** options legally want an **FCC Part 15B SDoC** first (`docs/COMPLIANCE.md`).
- [ ] Keep the **"honest specs"** framing (accuracy vs resolution; not a certified instrument) — it
      prevents returns and builds trust with technical buyers.

Store approval is typically **under 48 hours** after you submit the listing. Tindie fee is **5% of the
order total**; listing is free.
