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
- A **label / QR sticker** on the unit. It shows the probe's name (like **Setpoint-9A3F2C**) and a **setup secret**. Keep this label — you'll use it during setup.

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
- **Pick your unit:** use the **°C / °F / K** buttons on the dashboard to choose how temperatures are shown. This changes the display only — your data is stored the same either way — and any temperature you type elsewhere (such as alert limits, Section 10) is understood in the unit you picked, so you never convert by hand.
- **See your limits on the chart:** when the chart is focused on a single probe, that probe's alert limits (Section 10) appear as shaded bands, so you can see at a glance how close the readings are to the line.
- **Recent events:** the dashboard keeps a short **Recent events** list — when a probe went over or under its limits, rose too fast, went offline, or came back to normal, each with the time it happened.
- **Battery level:** a battery-powered probe that reports its charge shows **Batt NN%** on its card, on the dashboard and on the Devices page. It turns amber when the battery drops below 20% — time to recharge.
- **Export to a spreadsheet:** click the **download** link on the dashboard to save **`temperature_log.csv`**. Open it in Excel or Google Sheets. Each row is a reading with a timestamp, the temperature in °C and °F, and which probe it came from. Grow-variant probes (see Section 11) also fill in **humidity** and **VPD** columns; those columns stay blank for temperature-only probes.
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

**Turn on notifications (Settings → Alerts):**

1. Open **Settings** and find the **Alerts** card.
2. Turn on **Enable alerts**.
3. Switch on **Email** and/or **Webhook**, and fill in the boxes that appear:
   - **Email:** your mail provider's server name (for example `smtp.gmail.com`) and port, your username and password, and the From and To addresses. If you've saved a password here before, leaving the password box blank keeps the saved one.
   - **Webhook:** paste a URL from Slack, Discord, Zapier or a similar service.
4. Click **Save**, then click **Send test**. A test message goes to every channel you switched on, so you know it works before you rely on it.

Alerts are spaced out (debounced) so you aren't flooded with repeats — **"Re-alert every"** sets how often you're reminded while a probe stays out of range, and the small **deadband** stops a probe sitting right on the line from alerting over and over. You can also be told when a probe **goes offline** and when it **returns to normal**, using the switches on the same card.

**Catch a failing fridge or freezer early (rate-of-change alert):** on the same Alerts card, **"Rate alert (°C rise)"** warns you when a probe's temperature *climbs quickly* — for example, rises 3 °C within 10 minutes — which a failing freezer does long before it crosses your maximum limit. Set it to **0** to turn it off (the default).

**Daily summary email:** with Email switched on, you can also turn on **"Send a daily summary email"** and pick the hour it's sent. You'll get one email a day with each probe's minimum, average and maximum — a nice way to confirm everything stayed in range without watching the dashboard.

---

## 11. Humidity & VPD (grow variant)

Some Setpoints ship with a **humidity sensor (SHT4x)** for grow tents and greenhouses — the "grow variant." These probes measure **temperature and humidity**, and the hub uses both to calculate **VPD**.

- **Which probes report it:** only grow-variant probes (the ones with the humidity sensor). Standard temperature-only probes show temperature just as before.
- **Where it shows:** when a probe reports humidity, its card on the dashboard adds a **Humidity** readout (in %) and a **VPD** readout (in kPa) next to the temperature.
- **What VPD means (for growers):** VPD (vapour pressure deficit) rolls temperature and humidity into one number, in kPa, that describes how much "drying power" the air has for your plants — most growers aim to keep it in a target band for healthy transpiration.
- **How VPD is worked out:** you don't set it up — the hub computes VPD automatically from each temperature + humidity reading. Growers who want the VPD to reflect leaf (not just air) temperature can apply a small **leaf-temperature offset** (about 2 °C is common) via an advanced hub setting; see the developer guide, [DEVELOPING.md](DEVELOPING.md).

**Humidity and VPD alerts.** Today, alert limits are for **temperature** (Section 10). Humidity and VPD are measured, shown on the dashboard, saved in your history, included in the spreadsheet export, and published over the API and MQTT — but you can't yet set alert limits on them. Humidity and VPD alert thresholds are on the roadmap for a future update.

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
Check its **power first**: is the light on? If it runs on a battery, check the battery level on its card and recharge if it's low. Then check **Wi-Fi** — did the router restart, or did the Wi-Fi name or password change? Once the probe is back, it carries on by itself. Battery probes even **back-fill the readings they saved up while out of reach**, so a gap on the chart usually fills itself in after they reconnect.

**The probe joined the wrong Wi-Fi (or my Wi-Fi changed).**
No reset button needed. **Unplug the probe for 10 seconds and plug it back in.** When it can't reach a usable network, the **`Setpoint-XXXXXX`** setup network reappears within about 30 seconds — join it and repeat the setup steps (Sections 4–5) to pick the right Wi-Fi.

**I can't find the `Setpoint-XXXXXX` setup network.**
The probe only broadcasts its setup network when it isn't connected to a Wi-Fi it knows. Unplug it for 10 seconds and plug it back in, then look again — the setup network appears within about 30 seconds whenever the probe can't join a saved network.

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
