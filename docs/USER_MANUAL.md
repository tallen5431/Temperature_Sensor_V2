# TempSensor User Manual

Welcome! TempSensor lets you watch the temperature of your fridge, freezer, fermentation vessel, server closet, greenhouse, or any room — live, on your own computer. Nothing goes to the cloud, and there is no account to create. This guide walks you through everything, one step at a time. No technical background is needed.

**You will need:**

- Your TempSensor PC (Windows, or Linux/macOS).
- One or more TempSensor sensors.
- Your home or office Wi-Fi name and password.
- A phone or laptop to help set up each probe.

---

## 1. What's in the box

- A **TempSensor** sensor with a temperature probe on a lead.
- A **USB power adapter** and cable.
- A **label / QR sticker** on the unit. It shows the probe's name (like **TempSensor-9A3F2C**) and a **setup secret**. Keep this label — you'll use it during setup.

---

## 2. Start the hub on your PC

1. On the TempSensor PC:
   - **Windows:** double-click **`Start.bat`**.
   - **Linux/macOS:** double-click or run **`Start.sh`**.
2. The very first time, it spends a minute setting itself up. That's normal. Later starts are instant.
3. Your web browser opens automatically to the dashboard at **http://localhost:8088**. If it doesn't open on its own, open your browser and type **http://localhost:8088** into the address bar.
4. If Windows asks about the firewall, click **Allow** — and make sure **Private networks** is checked. This lets your probes reach the hub.

Leave this program running whenever you want to collect temperatures.

---

## 3. Power on the probe

1. Plug the TempSensor into the USB power adapter and into a wall outlet (or a USB battery pack).
2. Place the metal probe tip where you want to measure — inside the fridge, in the fermenter, etc.
3. A light on the unit indicates it has power.

The **first time** a probe is powered (or before it knows your Wi-Fi), it creates its own temporary setup network so you can tell it which Wi-Fi to join.

---

## 4. Join the probe's setup Wi-Fi (TempSensor SoftAP)

1. On your phone or laptop, open the **Wi-Fi settings**.
2. Look for a network named **`TempSensor-XXXXXX`** (the same code as on the unit's label).
3. Connect to it. It's an **open** network — there's no password to type. Just tap it and connect.

You are now connected directly to the probe. Your phone may warn that this network "has no internet" — that's expected during setup.

---

## 5. Choose your home Wi-Fi

1. A setup page should open automatically. If it doesn't, open a browser and go to **http://192.168.4.1**.
2. You'll see a list of nearby Wi-Fi networks. **Tap your home/office Wi-Fi.**
3. Enter your Wi-Fi password and confirm.
4. The probe saves the network and restarts. Your phone will drop the temporary `TempSensor-XXXXXX` network — that's a good sign. **Reconnect your phone to your normal Wi-Fi.**

The probe now joins your Wi-Fi on its own every time it powers on. You won't need to repeat this unless you change your Wi-Fi.

---

## 6. See the probe on the dashboard

1. Back on the TempSensor PC, go to **http://localhost:8088**.
2. Within a few seconds, your probe appears by name (for example **TempSensor-9A3F2C**), and its current temperature and a live chart begin updating.

That's it — the hub found the probe and set it up for you automatically. Readings continue as long as both the probe and the hub are powered on.

> **If nothing shows up after a minute,** see the Troubleshooting section at the end.

---

## 7. Read and export your data

- **Live view:** each probe shows its current temperature, a chart over time, and summary statistics.
- **Export to a spreadsheet:** click the **download** link on the dashboard to save **`temperature_log.csv`**. Open it in Excel or Google Sheets. Each row is a reading with a timestamp, the temperature in °C and °F, and which probe it came from. Grow-variant probes (see Section 11) also fill in **humidity** and **VPD** columns; those columns stay blank for temperature-only probes.

Your data lives only on this PC, in a local database. Backing it up is as simple as exporting the CSV from the dashboard (or downloading a full database backup).

---

## 8. Name your probes

Default names like `TempSensor-9A3F2C` are hard to remember. Give each probe a friendly name:

1. On the dashboard, find the probe.
2. Open its settings and type a name such as **"Kitchen fridge"** or **"Greenhouse"**.
3. Save. The new name appears everywhere, including in the exported spreadsheet.

---

## 9. Calibrate a probe (ice-bath, one-point)

Every temperature sensor is slightly off. A quick **ice-bath calibration** corrects a probe so it reads a known reference — 0 °C (32 °F) — accurately.

**What you need:** a glass or cup, ice, and cold water.

1. Fill the glass with **crushed or small ice**, then add cold water until it's slushy. Stir and let it sit for **2–3 minutes**. This mixture is very close to exactly **0 °C**.
2. Put the probe tip into the middle of the ice slush (not touching the sides or bottom). Stir gently.
3. Wait until the reading on the dashboard **stops changing** (about a minute).
4. Note what the probe reads. If it reads **0 °C**, you're done. If it reads, say, **0.6 °C**, it is reading **0.6° too high**.
5. In the probe's calibration setting, enter a matching **offset** so the corrected reading becomes **0 °C**. In the example above you'd apply an offset of **−0.6 °C**.
6. Save, and confirm the probe now reads **0 °C** in the ice bath.

From now on all of that probe's readings are corrected automatically before they're recorded.

---

## 10. Set temperature alerts

Get warned when a probe goes out of a safe range (for example, a fridge that gets too warm).

1. On the dashboard, open the alert settings for a probe (or the default that applies to all probes).
2. Set a **minimum** and **maximum** temperature. For a typical fridge, many people use about **2 °C to 8 °C**.
3. Save.

When a reading crosses your limits, TempSensor can notify you. To receive emails or a webhook alert, an installer or maker needs to fill in the notification settings (email server or webhook address) once; see the developer documentation. Alerts are spaced out (debounced) so you aren't flooded with repeats.

---

## 11. Humidity & VPD (grow variant)

Some TempSensors ship with a **humidity sensor (SHT4x)** for grow tents and greenhouses — the "grow variant." These probes measure **temperature and humidity**, and the hub uses both to calculate **VPD**.

- **Which probes report it:** only grow-variant probes (the ones with the humidity sensor). Standard temperature-only probes show temperature just as before.
- **Where it shows:** when a probe reports humidity, its card on the dashboard adds a **Humidity** readout (in %) and a **VPD** readout (in kPa) next to the temperature.
- **What VPD means (for growers):** VPD (vapour pressure deficit) rolls temperature and humidity into one number, in kPa, that describes how much "drying power" the air has for your plants — most growers aim to keep it in a target band for healthy transpiration.
- **How VPD is worked out:** you don't set it up — the hub computes VPD automatically from each temperature + humidity reading. A grower can optionally have an installer set a small **leaf-temperature offset** (growers commonly use about 2 °C) so the VPD reflects leaf, not just air, temperature.

**Humidity and VPD alerts.** In a grow-variant probe's alert settings (Section 10) you can set a **humidity minimum/maximum** (in %) and a **VPD minimum/maximum** (in kPa) alongside the temperature limits. TempSensor checks each one independently, so you can be warned if humidity or VPD drifts out of range even while the temperature is fine — with the same email/webhook notifications.

---

## 12. Troubleshooting FAQ

**The dashboard won't open at http://localhost:8088.**
Make sure the hub program (`Start.bat` / `Start.sh`) is still running. Look for its window. If it closed, start it again.

**My probe never appears on the dashboard.**
- Confirm the probe has power (check the light).
- Make sure it finished the Wi-Fi setup (Sections 4–5) and is on the **same** Wi-Fi as the hub PC.
- Wait up to a minute — the hub configures new probes automatically on a short cycle.
- Restart the probe by unplugging it for 10 seconds and plugging it back in.

**I can't find the `TempSensor-XXXXXX` setup network.**
The probe only broadcasts its setup network when it doesn't yet know a Wi-Fi. Unplug it for 10 seconds and plug it back in, then look again. If it already joined a Wi-Fi you no longer use, you may need to reset it (see the unit's label/insert).

**The setup page at http://192.168.4.1 doesn't load.**
Confirm your phone is connected to the `TempSensor-XXXXXX` network (not your home Wi-Fi), then reload the page.

**The probe shows a strange value like 85 °C or −127 °C.**
Those are sensor fault readings, usually from a loose or disconnected probe tip. TempSensor ignores them automatically. Check that the probe lead is firmly seated; if it persists, the sensor may need attention.

**Windows firewall blocked something.**
Re-run the hub and click **Allow** on **Private networks** when prompted. Without this, probes on your network can't reach the hub.

**Where is my data stored?**
In a local SQLite database called **`temperature_log.db`** in the TempSensor folder on your PC. You can export it anytime to a **`temperature_log.csv`** spreadsheet from the dashboard. Nothing is uploaded anywhere.

---

Need more detail or building your own hardware? See the [README](../README.md) and the developer guide, [DEVELOPING.md](DEVELOPING.md).
