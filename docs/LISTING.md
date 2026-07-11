# Online Store Listing — ThermaProbe (Homelab / Server-Room edition)

> _Selling on **Tindie**? See [`TINDIE_LISTING.md`](TINDIE_LISTING.md) — the same copy mapped
> field-by-field onto Tindie's listing form, with kit/assembled options and the exclusivity/FCC notes._

> _**Maker note (delete before publishing):** this is a ready-to-paste template for the **lead
> product** — the always-on, USB-powered, DS18B20 temperature probe aimed at homelab / server-room
> buyers. Replace **ThermaHub**/**ThermaProbe** with your brand, set your real **price**, drop in your
> **photos** and **support link** (`https://example.com/support`), and confirm the spec numbers match
> the exact unit you ship. Keep the "Honest specs" section — it prevents returns and builds trust with
> technical buyers. Do not add "no subscription" as the headline (every competitor already claims it);
> lead with **local / can't-be-bricked**._

---

## Title (benefit-led)

**ThermaProbe — Wi-Fi Temperature Monitor for Homelabs & Server Rooms · 100% Local, No Cloud, No Account · Prometheus + Home Assistant Ready**

_Alternate titles:_
- **ThermaProbe — Self-Hosted Wi-Fi Temperature Sensor · Runs on Your Own PC · Grafana / Home Assistant / MQTT**
- **ThermaProbe — Local-First Server-Room & Rack Temperature Monitor (No Cloud, No Subscription)**

---

## Hook

Know the instant your rack, closet, or NAS gets too hot — without handing your data to somebody
else's cloud. ThermaProbe reports to a small app on **your own** PC or server, so your readings never
leave the building and your alerts keep working even when the internet doesn't.

---

## Why it's different

- 🔒 **It can't be shut down.** The probe reports to a hub app you run yourself, and the firmware is
  open. No vendor account to close, no server to sunset — if the company that sold it to you vanishes,
  your setup keeps running. (Cloud thermometers have bricked overnight when their servers went dark.)
- 🏠 **Your data stays on-prem.** Readings are stored in a local **SQLite database on your machine**,
  exportable to CSV anytime — no account, no telemetry, nothing phoning home. Built for
  security-sensitive IT, OT, and home networks.
- 🧩 **Drops into the stack you already run** (see below) instead of being one more walled-garden app.
- 🌡️ **One hub, many probes.** Add probes and they self-discover on your LAN — pay for sensors, not for
  a per-sensor "gateway."
- 🛎️ **Alerts that reach you.** Set a high/low threshold per probe and get an **email or webhook** when
  it's breached — evaluated on the hub, so it fires even with no dashboard tab open.
- 🆓 **No subscription, ever.** The hub software is free; the probe is a one-time buy. _(Supporting perk —
  the real reason to choose it is the two points above.)_

## Drops into your homelab stack

- **Prometheus / Grafana** — scrape `http://<hub>:8088/metrics` for per-probe temperature + health gauges.
- **Home Assistant / MQTT** — flip on MQTT and each probe appears automatically as a temperature sensor
  (HA auto-discovery).
- **Docker / headless** — `docker compose up -d` runs the hub on your NAS or server; data persists in a
  mounted volume.
- **Plain CSV export** — one click pulls the full log into Excel, Sheets, or your own scripts.
- **Optional dashboard login** — turn on HTTP Basic auth for a shared office/lab LAN.

---

## Honest specs

| Spec | ThermaProbe (standard) |
|---|---|
| Sensor | Maxim **DS18B20**, waterproof stainless probe (1 m lead) |
| **Accuracy** | **±0.5 °C typical (−10 to +85 °C), uncalibrated.** Add a per-probe offset in the app to trim to your reference. |
| Resolution | 0.0625 °C (12-bit) — _resolution, not accuracy_ |
| Sensor range | −55 to +125 °C (−67 to +257 °F) |
| Connectivity | **2.4 GHz** Wi-Fi (802.11 b/g/n). _No 5 GHz — put it on a 2.4 GHz SSID._ |
| Power | USB, 5 V (**always-on** — this model does not run on battery) |
| Reporting interval | Configurable, 1 s to 1 hour (default 5 s) |
| Probes per hub | Many (dozens) — one hub serves your whole rack/closet/site |
| Data storage | Local **SQLite database** on your PC (one-click CSV export) — no cloud, no account |
| Hub software | Free. **Windows 10/11 or Linux**; installs its own runtime. Runs headless / in Docker on a NAS. |
| Integrations | Prometheus `/metrics`, MQTT + Home Assistant auto-discovery, CSV export, email/webhook alerts |
| Firmware | Open source; on-device Wi-Fi setup (no app store, no account) |

> **Needs an always-on computer on the same network** (a PC, mini-PC, NAS, or home server) to run the
> free hub and store data. If you don't already leave a machine on 24/7, this isn't the right pick.

---

## What's in the box

- 1× ThermaProbe unit (ESP32 + waterproof DS18B20 probe in an enclosure)
- 1× USB power cable
- 1× quick-start card (join Wi-Fi → open dashboard → done) + link to the full user manual
- Unit label with its serial ID, setup Wi-Fi name & password, and a setup QR code

_(The hub app is a free download — no disc, no account.)_

---

## Product-photo shot list

1. **Hero** — the unit on a clean surface, probe lead coiled, on a neutral/dark background.
2. **In context** — probe tip clipped inside an open server rack or wiring closet, unit velcro'd to the rail.
3. **Scale shot** — unit in hand (conveys the small size).
4. **The probe tip** — macro of the stainless waterproof tip.
5. **Dashboard screenshot** — the live web dashboard on a laptop showing a temperature chart + gauge.
6. **Integration screenshot** — the same probe shown in **Grafana** (or Home Assistant) to prove "drops into your stack."
7. **Multi-probe** — 3–4 units together (sells the rack/kit upsell).
8. **What's-in-the-box flat-lay** — unit, cable, quick-start card, label/QR.
9. **Setup GIF / short video** — join the probe's Wi-Fi → pick your network → it appears on the dashboard.
10. **Label close-up** — showing the serial ID + setup QR (signals per-unit quality/traceability).

---

## FAQ

**How accurate is it?** ±0.5 °C typical, uncalibrated — fine for "is my rack/closet within range and
trending safe." You can set a per-probe calibration offset in the app to trim it to a reference
thermometer. It is **not** a certified, NIST-traceable, or medical/lab instrument.

**Does it need the internet or an account?** No. It talks only to the hub on your local network. No
account, no cloud, no telemetry. Internet is only needed if you want *email* alerts to leave your LAN.

**What do I need to run it?** An always-on Windows or Linux computer (PC, mini-PC, NAS, or home server)
on the same Wi-Fi/LAN. The hub is a free download and installs its own runtime; it also runs headless
in Docker.

**Will it work on my Wi-Fi?** It uses **2.4 GHz** Wi-Fi (not 5 GHz) — make sure a 2.4 GHz network is
available. Setup is on-device (join the probe's temporary network, pick yours) — no phone app required.

**How many probes can one hub handle?** Many — dozens. One hub covers a whole rack, closet, or several
rooms; buy additional probes as you grow.

**Does it keep alerting if my internet goes down?** Yes — alerts are evaluated locally on the hub, so
LAN webhooks keep firing during a WAN outage. **But nothing survives a full power loss** — the probe,
your Wi-Fi, and the hub all need power, so put your router/hub on a **UPS** if outages are the risk you
care about.

**Can I get my data out?** Anytime — one click exports the full history as CSV. It's your file on your
disk; there's nothing to unlock or migrate.

**Is the firmware really open?** Yes — you can read it, build it, and reflash it. You're never locked to
us.

---

## Honest claims (keep this)

ThermaProbe is a general-purpose monitoring device. Stated accuracy (±0.5 °C typical) is the sensor's
uncalibrated datasheet figure — resolution (0.0625 °C) is not accuracy. It is **not** a certified,
NIST-traceable, medical, food-safety, or regulatory-compliance instrument, and is not sold for those
uses. Local alerting depends on power to the probe, your network, and the hub; pair it with a UPS if
power-loss detection matters.
