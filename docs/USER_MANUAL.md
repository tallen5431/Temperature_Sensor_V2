# Setpoint User Manual

Welcome! Setpoint lets you watch the temperature of your fridge, freezer, fermentation vessel, server closet, greenhouse, or any room — live, on your own computer. Nothing goes to the cloud, and there is no account to create. This guide walks you through everything, one step at a time. No technical background is needed.

**You will need:**

- Your Setpoint PC (Windows, or Linux/macOS).
- One or more Setpoint sensors.
- Your home or office Wi-Fi name and password.
- A phone or laptop to help set up each probe.

---

## 1. What's in the box

- A **Setpoint** sensor with a temperature probe on a lead.
- A **USB power adapter** and cable.
- A **label / QR sticker** on the unit. It shows the probe's name (like **Setpoint-9A3F2C**), which is also the name of its setup Wi-Fi network, and a QR code to the setup page. There is **no password or secret** on the label — the setup network is open (Section 4). Keep the label anyway: the name on it is how you identify this probe on the dashboard and in support requests.

---

## 2. Start the hub on your PC

1. On the Setpoint PC:
   - **Windows:** double-click **`Start.bat`**.
   - **Linux/macOS:** double-click or run **`Start.sh`**.
2. The very first time, it spends a minute setting itself up. That's normal. Later starts are instant.
3. Your web browser opens automatically to the dashboard at **http://localhost:8088**. If it doesn't open on its own, open your browser and type **http://localhost:8088** into the address bar.
4. If Windows asks about the firewall, click **Allow** — and make sure **Private networks** is checked. This lets your probes reach the hub.

Leave this program running whenever you want to collect temperatures.

---

## 3. Power on the probe

1. Plug the Setpoint into the USB power adapter and into a wall outlet (or a USB battery pack).
2. Place the metal probe tip where you want to measure — inside the fridge, in the fermenter, etc.
3. A light on the unit indicates it has power.

The **first time** a probe is powered (or before it knows your Wi-Fi), it creates its own temporary setup network so you can tell it which Wi-Fi to join.

---

## 4. Join the probe's setup Wi-Fi (Setpoint SoftAP)

1. On your phone or laptop, open the **Wi-Fi settings**.
2. Look for a network named **`Setpoint-XXXXXX`** (the same code as on the unit's label).
3. Connect to it. It's an **open** network — there's no password to type. Just tap it and connect.

You are now connected directly to the probe. Your phone may warn that this network "has no internet" — that's expected during setup.

---

## 5. Choose your home Wi-Fi

1. A setup page should open automatically. If it doesn't, open a browser and go to **http://192.168.4.1**.
2. You'll see a list of nearby Wi-Fi networks. **Tap your home/office Wi-Fi.**
3. Enter your Wi-Fi password and confirm.
4. The probe saves the network and restarts. Your phone will drop the temporary `Setpoint-XXXXXX` network — that's a good sign. **Reconnect your phone to your normal Wi-Fi.**

The probe now joins your Wi-Fi on its own every time it powers on. You won't need to repeat this unless you change your Wi-Fi.

---

## 6. See the probe on the dashboard

1. Back on the Setpoint PC, go to **http://localhost:8088**.
2. Within a few seconds, your probe appears by name (for example **Setpoint-9A3F2C**), and its current temperature and a live chart begin updating.

That's it — the hub found the probe and set it up for you automatically. Readings continue as long as both the probe and the hub are powered on.

> **If nothing shows up after a minute,** see the Troubleshooting section at the end.

---

## 7. Read and export your data

- **Live view:** each probe shows its current temperature, a chart over time, and summary statistics.
- **Pick your unit:** the dashboard starts in the unit your computer already uses — °F and a 12-hour clock in the United States, °C and a 24-hour clock nearly everywhere else — so there is usually nothing to set. The **°C / °F / K** and **24h / 12h** buttons in the toolbar override that, and your choice is remembered in that browser. It changes the display only — your data is stored the same either way — and any temperature you type elsewhere (such as alert limits, Section 10) is understood in the unit you picked, so you never convert by hand.
- **See your limits on the chart:** when the chart is focused on a single probe, that probe's alert limits (Section 10) appear as shaded bands, so you can see at a glance how close the readings are to the line.
- **More detail:** below the statistics, the **More detail** link opens the extras — a **per-probe breakdown** of min/average/max, humidity readouts for probes that measure it, and a short **Recent events** list showing when a probe went over or under its limits, rose too fast, went offline, or came back to normal. It stays open once you open it, so the dashboard shows either the short version or the full one, whichever you prefer.
- **Battery level:** if a probe reports its charge, **Batt NN%** appears on its card, on the dashboard and on the Devices page, turning amber below 20%. **Setpoint probes do not report it yet** — the hub supports it (`PROTOCOL.md` §7) but the rev-1 and rev-2 boards have no battery-sense circuit, so no **Batt** figure is shown. Judge remaining charge from the charger's own LED instead.
- **Export to a spreadsheet:** click **Export…** on the dashboard, pick a probe and (optionally) a date range, then choose a **format** and download:
    - **Excel-friendly CSV** (recommended) — opens straight into Excel or Google Sheets ready to work with: the **date** and **time** are in their own columns so you can sort and filter them like normal dates, each probe shows the **friendly name** you gave it, and the clutter columns are left out. This is the easiest choice for most people.
    - **Excel workbook (`.xlsx`)** — a real Excel file: double-click and the dates, times and temperatures are already the right types, with a frozen header row and filter buttons. (For very large date ranges, use a CSV instead — a single Excel sheet can't hold more than about a million rows.)
    - **Raw CSV** — the complete, unabbreviated file (full ISO timestamps and every column; the humidity/VPD columns are present but stay empty until a humidity-capable probe exists — see Section 11). Best if you feed the data into another program or re-import it later.
  <br>Each row is one reading with the temperature in °C and °F and which probe it came from; every format also includes an exact **UTC** timestamp so the data stays correct across computers and daylight-saving changes.
- **Home Assistant (MQTT):** if you use Home Assistant, open **Settings → Integrations**, switch on **Publish to MQTT**, enter your broker's address, and click **Save**. Each probe then appears in Home Assistant automatically (auto-discovery) — it's all done from the Settings page, with no configuration files to edit.
- **Put it on your phone:** open the dashboard in your phone's browser — use the Setpoint PC's network address instead of `localhost`, for example `http://192.168.1.50:8088` — then choose your browser's **Add to Home Screen** option. The dashboard installs like an app and opens full-screen from its own icon.

Your data lives only on this PC, in a local database. Backing it up is as simple as exporting the CSV from the dashboard (or downloading a full database backup).

---

## 8. Name your probes

Default names like `Setpoint-9A3F2C` are hard to remember. Give each probe a friendly name:

1. Open the **Devices** page and find the probe's card.
2. Click **Edit** next to the probe's name.
3. Type a name such as **"Kitchen fridge"** or **"Greenhouse"** into **Friendly Name**.
4. Click **Save**. The new name appears everywhere, including in the exported spreadsheet.

> **Why a setting can take a while to take effect.** The friendly name is stored on
> the hub and applies instantly. Settings that live *on the probe* — the reading
> interval and the sensor resolution — are different: a battery probe sleeps between
> readings to save power, and it collects new settings when it next wakes up and
> reports in. So if it reports once an hour, your change takes effect within the hour,
> not immediately. The Devices page tells you the time to expect it by when you save.
> While the probe is asleep the hub has no way to reach it, so it cannot confirm the
> change has landed until the probe next reports — that is normal, not a fault.
>
> If you have switched **automatic provisioning off** in Settings, the hub stops
> sending settings to probes altogether, and interval/resolution changes will **never**
> reach them. The Devices page warns you when you save in that state.

---

## 9. Calibrate a probe (ice-bath, one-point)

Every temperature sensor is slightly off. A quick **ice-bath calibration** corrects a probe so it reads a known reference — 0 °C (32 °F) — accurately.

**What you need:** a glass or cup, ice, and cold water.

1. Fill the glass with **crushed or small ice**, then add cold water until it's slushy. Stir and let it sit for **2–3 minutes**. This mixture is very close to exactly **0 °C**.
2. Put the probe tip into the middle of the ice slush (not touching the sides or bottom). Stir gently.
3. Wait until the reading on the dashboard **stops changing** (about a minute).
4. Note what the probe reads. If it reads **0 °C**, you're done. If it reads, say, **0.6 °C**, it is reading **0.6° too high**.
5. Open the **Devices** page, click **Edit** on the probe, and enter a matching **Calibration Offset** so the corrected reading becomes **0 °C**. In the example above you'd apply an offset of **−0.6 °C**. (The offset box uses whichever unit the dashboard is showing.)
6. Click **Save**, and confirm the probe now reads **0 °C** in the ice bath.

From now on all of that probe's readings are corrected automatically before they're recorded.

---

## 10. Set temperature alerts

Get warned when a probe goes out of a safe range (for example, a fridge that gets too warm).

**Set the limits (per probe):**

1. Open the **Devices** page and click **Edit** on the probe.
2. Under **Alert Thresholds**, enter a **minimum** and **maximum** temperature. For a typical fridge, many people use about **2 °C to 8 °C** (36 °F to 46 °F). You type the numbers in whichever unit the dashboard is currently showing (°C, °F or K) — no converting needed.
3. Click **Save**. Leave both boxes blank to turn threshold alerts off for that probe.

When a reading crosses your limits, the dashboard shows the breach right away. To also get an **email or webhook message**, turn on notifications:

**Turn on notifications (Settings → Alerts & notifications):**

The Settings page is a list of sections, each showing what it is currently set to. Click one to open it.

1. Open **Settings** and click **Alerts & notifications**.
2. Turn on **Enable alerts**.
3. Switch on **Email** and/or **Webhook**, and fill in the boxes that appear:
   - **Email:** type your **email address** and its **password** — that's all. The hub recognises the address and fills in the mail server, port and encryption for you, and sends the alerts to that same address unless you enter someone else in **Send alerts to**. If you've saved a password here before, leaving the password box blank keeps the saved one.
   - **Webhook:** paste a URL from Slack, Discord, Teams, Zapier or a similar service. The hub names the service back to you so you know it recognised it.
4. Click **Save**, then click **Send test**. A test message goes to every channel you switched on, so you know it works before you rely on it.

> **If your provider needs an "app password".** Gmail, Yahoo, iCloud, Fastmail and
> others reject your normal account password from programs like this and require a
> separate app password generated in your account's security settings. When you type
> an address at one of those providers, the hub says so on the spot — that message is
> the most common reason a correct-looking email setup never delivers.
>
> Using your own mail server, or a provider the hub doesn't recognise? Open **Server
> settings** under the password box and enter the host, port and encryption yourself.
> Anything you type there is kept exactly as you typed it.

You can also be told when a probe **stops reporting**, using the switch under *When to send them*.

**Fine-tuning (Advanced settings):** everything else already has a sensible default, and lives behind **Advanced settings** at the bottom of the Alerts section for when a deployment alerts too often or not soon enough:

- **"Re-alert every"** — how often you're reminded while a probe stays out of range.
- **Deadband** — stops a probe sitting right on the line from alerting over and over.
- **"Notify when a probe returns to normal"**, and how long the hub waits before it believes a flaky probe is really back.
- **"Offline after"** — how long a probe may go quiet before it counts as offline. Probes that report on a slower cadence get proportionally longer automatically, so this rarely needs touching.
- **"Rate alert (°C rise)"** — warns you when a probe's temperature *climbs quickly*, for example rises 3 °C within 10 minutes, which a failing freezer does long before it crosses your maximum limit. **0** turns it off (the default).

**Daily summary email:** with Email switched on, you can also turn on **"Also send a daily summary email"** and pick the hour it's sent. You'll get one email a day with each probe's minimum, average and maximum — a nice way to confirm everything stayed in range without watching the dashboard.

---

## 11. Humidity & VPD (not yet available)

> **No shipping Setpoint measures humidity today.** The grow variant described here is a
> **planned** product, not one you can buy or build: firmware v2.8.2 has no SHT4x support and no
> shipping unit is populated with the sensor (see [`BOM.md`](BOM.md)). The *hub* side is already
> built and waiting — storage, dashboard readouts, VPD maths, CSV export, API and MQTT all handle
> humidity the moment a probe reports it — which is why this section exists. Read it as a
> description of what will happen when the hardware lands, not as a feature to look for on your
> unit. If your probe shows no Humidity readout, nothing is wrong with it.

The planned grow variant adds a **humidity sensor (SHT4x)** for grow tents and greenhouses. Those
probes will measure **temperature and humidity**, and the hub uses both to calculate **VPD**.

- **Which probes will report it:** only grow-variant probes (the ones with the humidity sensor). Standard temperature-only probes — which is every unit shipping today — show temperature just as before.
- **Where it will show:** when a probe reports humidity, its card on the dashboard adds a **Humidity** readout (in %) and a **VPD** readout (in kPa) next to the temperature.
- **What VPD means (for growers):** VPD (vapour pressure deficit) rolls temperature and humidity into one number, in kPa, that describes how much "drying power" the air has for your plants — most growers aim to keep it in a target band for healthy transpiration.
- **How VPD is worked out:** you don't set it up — the hub computes VPD automatically from each temperature + humidity reading. Growers who want the VPD to reflect leaf (not just air) temperature can apply a small **leaf-temperature offset** (about 2 °C is common) via an advanced hub setting; see the developer guide, [DEVELOPING.md](DEVELOPING.md).

**Humidity and VPD alerts.** Alert limits are for **temperature** only (Section 10). Once humidity hardware exists, its readings will be shown on the dashboard, saved in your history, included in the spreadsheet export, and published over the API and MQTT — but you can't yet set alert limits on them. Humidity and VPD alert thresholds are on the roadmap for a future update.

---

## 12. Troubleshooting FAQ

**The dashboard won't open at http://localhost:8088.**
Make sure the hub program (`Start.bat` / `Start.sh`) is still running. Look for its window. If it closed, start it again.

**My probe never appears on the dashboard.**
- Confirm the probe has power (check the light).
- Make sure it finished the Wi-Fi setup (Sections 4–5) and is on the **same** Wi-Fi as the hub PC.
- Wait up to a minute — the hub configures new probes automatically on a short cycle.
- Restart the probe by unplugging it for 10 seconds and plugging it back in.

**A probe shows "stale" or "offline" on the dashboard.**
Check its **power first**: is the light on? If it runs on a battery, recharge it — the probe reports no battery figure to the hub, so a flat cell looks exactly like a probe that went offline. Then check **Wi-Fi** — did the router restart, or did the Wi-Fi name or password change? A **router restart or brief outage fixes itself**: the probe keeps trying its saved network and rejoins on its own (it will *not* jump to its own setup network over a passing hiccup), then battery probes **back-fill the readings they saved up while out of reach**, so a gap on the chart usually fills itself in. If you actually **changed your Wi-Fi name or password**, the probe can't rejoin the old network — put it back into setup mode (next answer).

**The probe joined the wrong Wi-Fi, or my Wi-Fi name/password changed.**
No reset button needed. The probe now tries hard to rejoin the network it already knows, so a single restart won't kick it into setup mode — that's deliberate, so a rebooting router doesn't turn it into an open Wi-Fi network. To force setup mode, **power-cycle it three times** (unplug ~10 seconds and plug back in, three times; give each try up to a minute). On the third boot that can't reach the saved network, the **`Setpoint-XXXXXX`** setup network reappears — join it and repeat the setup steps (Sections 4–5) to pick the right Wi-Fi.

**I can't find the `Setpoint-XXXXXX` setup network.**
The probe only broadcasts its setup network during first-time setup, or after it fails to reach a saved network on **three power-cycles in a row** (see the previous answer). Power-cycle it a few more times — unplug ~10 seconds each time, allowing up to a minute per try — and look again; once it gives up on the saved network the setup network appears.

**The setup page at http://192.168.4.1 doesn't load.**
Confirm your phone is connected to the `Setpoint-XXXXXX` network (not your home Wi-Fi), then reload the page.

**The probe shows a strange value like 85 °C or −127 °C.**
Those are sensor fault readings, usually from a loose or disconnected probe tip. Setpoint ignores them automatically. Check that the probe lead is firmly seated; if it persists, the sensor may need attention.

**Windows firewall blocked something.**
Re-run the hub and click **Allow** on **Private networks** when prompted. Without this, probes on your network can't reach the hub.

**Where is my data stored?**
In a local SQLite database called **`temperature_log.db`** in the Setpoint folder on your PC. You can export it anytime to a **`temperature_log.csv`** spreadsheet from the dashboard. Nothing is uploaded anywhere.

---

Need more detail or building your own hardware? See the [README](../README.md) and the developer guide, [DEVELOPING.md](DEVELOPING.md).
