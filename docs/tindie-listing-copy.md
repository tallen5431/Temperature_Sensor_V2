# Tindie listing — paste-ready copy

> Keep this in sync with `docs/TINDIE_LISTING.md` (the field-by-field mapping) and with
> the accuracy wording in `docs/WARRANTY.md` and `site/index.html`. If the accuracy band
> changes in one place it must change in all four.
>
> **Status: this copy is LIVE on the listing as of 2026-08-03.** Edit here first, then paste.
>
> `support@datumlaboratories.com` resolves (Zoho alias, delivery confirmed), so it is safe in
> Tindie's support field — see the checklist in `docs/TINDIE_LISTING.md`. Tindie's own
> *Ask a Question* / *Contact Store* flow stays available either way.

---

## Product Title — **do not change**

```
Setpoint DIY Kit — Local Wi-Fi Temperature Monitor
```

Tindie warns on the edit page that *"Changing the title will change the product link."*
The current slug already ranks — searching "Setpoint DIY Kit" returns it — and the URL is
hard-linked from `site/index.html` twice (the visible CTA and the `Product`/`Offer` JSON-LD).
Renaming for keywords trades a ranking that exists for one that might. Leave it.

## 140-character description (138 chars)

```
Wi-Fi temperature alarm kit for freezers, fridges & racks. Reports to a free app on your PC. No cloud. Home Assistant / Prometheus / MQTT.
```

This field is the one worth optimising — it carries "freezer" and "alarm," the highest-intent
terms, and changing it does not touch the URL.

## Product Description

**Know the instant your freezer, fridge, or rack swings out of range — without handing your data to somebody else's cloud.** Setpoint is a Wi-Fi temperature probe that reports to a small, free app you run on **your own** PC, mini-PC, or NAS. Your readings never leave the building, and your alerts keep working even when the internet doesn't.

*Built by a solo maker who got tired of "smart" thermometers that phone home, lock you into an app, and brick when the vendor's servers go dark.*

### Why it's different
- 🔒 **It can't be shut down.** The probe reports to a hub app you run yourself, and the firmware is open. No vendor account to close, no server to sunset.
- 🏠 **Your data stays on-prem.** Readings live in a local SQLite database on your machine, exportable to CSV/Excel anytime. No account, no telemetry, nothing phoning home.
- 🧩 **Drops into your stack:** Prometheus `/metrics`, plus Home Assistant + MQTT auto-discovery (each probe auto-appears as a sensor). Runs headless / in Docker.
- 🖥️ **Flash it from your browser.** No Arduino, no drivers, no toolchain — plug in USB-C, click once on the web flasher (Chrome/Edge), done.
- 🌡️ **One hub, many probes.** Add probes and they self-discover on your LAN — pay for sensors, not a per-sensor gateway.
- 🛎️ **Alerts that reach you.** Per-probe high/low thresholds → email or webhook, evaluated on the hub so they fire even with no dashboard open.

### Honest specs
- **Sensor:** DS18B20 waterproof stainless probe (1 m lead)
- **Accuracy:** **±0.5 °C typical from −10 °C to +85 °C**, uncalibrated. **Below −10 °C — which includes a typical −18 °C freezer — it's ±2 °C.** That's enough to tell you a freezer has failed, which is what an alarm is for; it is *not* a calibrated record at a frozen-storage threshold, and I don't sell it as one. Add a per-probe offset in the app to tighten it against a known reference. Resolution 0.0625 °C is *not* accuracy.
- **Wi-Fi:** 2.4 GHz only. On-device setup — no phone app.
- **Power:** rechargeable 18650 via a TP4056 charge/protect board, deep-sleeps between reads. **Cell not included** (lithium shipping rules).
- **Data:** local SQLite; one-click CSV / Excel export.
- **Hub software:** free download (Windows 10/11 or Linux; runs headless / in Docker). Dashboard opens at `http://localhost:8088`.

**Needs an always-on computer** on the same network to run the free hub. If you don't already leave a machine on 24/7, this isn't the right pick.

### What's in the kit (you solder + flash it)
Carrier PCB · ESP32-C3 SuperMini · waterproof DS18B20 probe (JST pre-terminated — no crimping) · 4.7 kΩ resistor · TP4056 charge/protect board · on/off switch · 18650 holder · headers · **USB-C data cable** · printed quick-start card with the browser-flash QR.

**Just add a battery:** one reputable 18650 (~2500–3500 mAh, flat-top or protected). Not included — the only part you supply.

### If something's wrong with the kit
A component that arrives dead, damaged, or missing is covered for **30 days** — tell me and I'll send a replacement. Test the DS18B20 first: a probe reading `−127` or blank is the most common bad part. Assembly faults aren't covered, because I can't warrant a build I didn't make. Full terms ship with the kit.

### FAQ
- **Needs internet/an account?** No — LAN only.
- **Accuracy?** ±0.5 °C typical from −10 to +85 °C; ±2 °C below that, including a typical freezer. Uncalibrated.
- **Can I use this for food-safety records?** No. Setpoint is a monitoring and temperature-logging **aid** — not a certified medical, food-safety or life-safety device, not a validated critical-control device, and not certified to EN 12830 or any equivalent. It doesn't replace required manual checks or official records.
- **Battery?** Runs on one 18650 (not included). Or run always-on from USB with no cell.
- **Open firmware?** Yes — read it, build it, reflash it. Never locked in.

*(The hub app is a free download — no account, nothing to install on the probe beyond the one-click flash.)*

---

Designed and built by **Datum Laboratories LLC** (Datum Labs) in Kennesaw, Georgia.
Docs, setup guide and the browser flasher: **https://datumlaboratories.com**
