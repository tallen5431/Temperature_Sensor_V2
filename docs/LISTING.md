# Online Store Listing Copy

> **Note for the maker/reseller:** ThermaHub is a white-label product. Replace
> **ThermaHub**/**ThermaProbe** with your product names, drop in your price,
> photos, and support link (`https://example.com/support`), and confirm the spec
> numbers match the exact hardware model you ship. Copy the sections below
> straight into your store listing.

---

## Title (benefit-led)

**ThermaHub — Wireless Temperature Monitor for Fridge, Freezer, Fermentation &
Server Closet | No Cloud, No Account, Runs on Your Own PC**

_Alternate shorter title:_
**ThermaHub Local Temperature Monitoring Kit — Private, No-Subscription, Your Data Stays Home**

---

## Short description (for listing summary / social)

Keep an eye on the temperatures that matter — your fridge, freezer, ferment,
greenhouse, or server closet — without handing your data to a cloud service.
ThermaHub runs on your own Windows or Linux PC. Wireless ThermaProbe sensors send
readings over your own network, and you watch everything live in your browser.
No account, no subscription, no telemetry. Ever.

---

## Full description

**Monitoring that respects your privacy.** Most "smart" temperature sensors push
your data to someone else's cloud and lock the useful parts behind a
subscription. ThermaHub does the opposite. It is a small app that runs on a
computer you already own, and everything stays there.

**Plug and play.** Power on a ThermaProbe, join it to your Wi-Fi from the setup
screen on the unit, and it shows up on the dashboard on its own — the hub finds
it and configures it for you. Add as many probes as you like.

**A live dashboard in your browser.** Open `http://localhost:8080` to see current
temperature, charts, and rolling statistics for every probe. Green when things
are fine, clear when they are not.

**Your data, in a plain file.** Every reading is logged to a simple
`temperature_log.csv` on your PC — one click to download for Excel, Google
Sheets, or your own analysis. No export fees, no data hostage.

**Calibrate and get alerted.** Trim each probe against a reference (an ice bath)
for accuracy, set high/low thresholds, and — optionally — get an email or webhook
alert when a temperature goes out of range. Alerts use *your* mail server or *your*
webhook; nothing routes through us.

**Private by design.** No account to create. No cloud service. No usage tracking.
The hub only ever talks to your own probes on your own network, secured with a
private device token it generates on first run.

Great for: refrigerators & freezers, beer/wine/kombucha fermentation, cheese and
curing, greenhouses and grow tents, server and network closets, wine fridges,
vaccine/medication fridges (as a monitoring aid), and any room you want to keep an
eye on.

> Note: ThermaHub is a monitoring aid, not a certified safety or medical device.

---

## Specifications

| Spec | Detail |
| --- | --- |
| Temperature range | -55 to +125 C (-67 to +257 F) with the standard DS18B20 probe; wider range with the optional MAX31855 thermocouple build |
| Sensor accuracy | +/-0.5 C typical (DS18B20) over 0-70 C; further improved with per-probe calibration (offset + gain) against a reference |
| Resolution | Down to 0.0625 C (sensor dependent) |
| Probes per hub | Unlimited in practice — add as many ThermaProbe sensors as your network supports |
| Connectivity | Wi-Fi 2.4 GHz (WPA2); probes report to the hub over your local network |
| Reading interval | Configurable (default every 5 seconds) |
| PC requirements | Windows 10/11 or Linux; any modern PC; ~200 MB free space; a web browser. No dedicated server needed |
| Software | Included, runs locally (Python app served on port 8080). MIT-licensed |
| Data storage | Local CSV file (`temperature_log.csv`) on your PC — timestamp, C, F, probe ID |
| Alerts | Optional email (your SMTP) and webhook, off by default |
| Data & privacy | No cloud, no account, no telemetry. Works fully offline |
| Setup | Captive-portal Wi-Fi setup on the probe; hub auto-discovers and configures |
| Power | USB-powered probes and hub host (adapter/battery depending on model) |

---

## What's in the box

- 1x ThermaHub setup guide with download/run instructions (software included, no
  disc needed)
- 1x or more ThermaProbe wireless temperature sensor(s), each with a DS18B20
  probe on a lead
- USB power cable(s) for the probe(s)
- Per-unit label/QR with the Wi-Fi setup network name, password, and provisioning
  secret
- Quick-start card pointing to the User Manual and support

_(Confirm exact contents and probe count for the specific kit you are selling.)_

---

## Product-photo shot list

1. **Hero shot** — the ThermaProbe (and hub host if applicable) cleanly lit on a
   neutral background, main marketing image.
2. **In context — fridge/freezer** — probe lead going into a refrigerator with the
   door ajar, dashboard visible on a laptop nearby.
3. **In context — fermentation / greenhouse** — probe near a fermenter or in a
   grow tent, showing the target buyer's use case.
4. **Dashboard screenshot** — the browser at `http://localhost:8080` showing live
   temperature, a chart, and multiple probes.
5. **Alert example** — a phone or inbox showing an out-of-range email/webhook
   alert (with a caption that alerts are optional and use your own mail/webhook).
6. **Setup flow** — the phone captive-portal Wi-Fi setup screen next to the probe,
   emphasizing "plug and play."
7. **What's in the box (flat lay)** — probe, cable, label/QR card, quick-start
   card laid out neatly.
8. **Privacy graphic** — a simple "No cloud - No account - No telemetry - Your PC"
   badge/diagram.
9. **Scale/size shot** — probe next to a common object (a coin or a hand) so
   buyers understand the size.
10. **CSV/export shot** — the downloaded `temperature_log.csv` open in a
    spreadsheet, reinforcing "your data, your file."

---

## Support & policies (link these on the listing)

- Support: **https://example.com/support**
- Privacy: `PRIVACY.md`
- Warranty: `docs/WARRANTY.md` (1-year limited hardware warranty)
- Returns & refunds: `docs/RETURNS.md` (30-day returns)
