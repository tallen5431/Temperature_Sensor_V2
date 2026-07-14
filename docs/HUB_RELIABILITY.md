# Setpoint — Keep the Hub Running (pilot & production installs)

> A homelabber will happily restart their own hub. A **restaurant won't** — staff reboot the PC,
> Windows installs updates overnight, someone closes the console window. If the hub app isn't running,
> **no readings are logged and no alerts fire** — a silent gap that turns a pilot into a bad first
> impression. This is the one-page SOP to make the hub survive reboots and neglect. Do it at every
> pilot install ([`PILOT_OFFER.md`](PILOT_OFFER.md)) and any always-on deployment.

The readings database is durable on disk, so history isn't lost on a reboot — but **new** data and
alerts only exist while the app is running. The whole job here is: **start on boot, stay up, and prove
it came back.**

---

## 1. Make it start on boot (pick your OS)

**Windows (most restaurant back-office PCs).**
- Easiest: the installer's **"Start automatically when I sign in"** checkbox
  ([`INSTALL.md`](INSTALL.md)). Good when the PC auto-logs-in to one account.
- More robust (survives with no user logged in): install it as a **Windows service** with
  [NSSM](https://nssm.cc/) — see [`packaging/README.md`](../packaging/README.md):
  ```
  nssm install SetpointHub "C:\Program Files\Setpoint\temperature-hub.exe"
  nssm start SetpointHub
  ```
- Set the PC's power plan to **never sleep**, and disable "fast startup" so a reboot fully relaunches.

**Linux (a mini-PC or Pi hub — the cleanest option).**
- Use the provided unit [`packaging/systemd/temperature-hub.service`](../packaging/systemd/temperature-hub.service):
  ```
  sudo cp packaging/systemd/temperature-hub.service /etc/systemd/system/
  sudo systemctl enable --now temperature-hub
  journalctl -u temperature-hub -f      # watch it run
  ```
- `Restart=on-failure` (in the unit) brings it back if it ever crashes.

**macOS.** Add the app to **System Settings → General → Login Items**, or run the onedir binary from a
`launchd` LaunchAgent plist. Disable App Nap for the process.

**Docker (if the site already runs containers).** The compose file sets it — just keep
`restart: unless-stopped` so the daemon relaunches it on boot/crash:
```
docker compose up -d
```

---

## 2. Let probes reach it

- **Firewall:** allow the hub app on **Private** networks (Windows prompts once — click *Allow*). If
  probes can't POST, the dashboard stays empty even though everything else is fine.
- **Fixed hostname/IP:** give the hub PC a **DHCP reservation** (or static IP) so a router reboot
  doesn't move it. Probes rediscover via mDNS, but a stable address makes support trivial.
- **One 2.4 GHz network:** confirm the probes' Wi-Fi reaches the walk-in (the #1 fixed-install gotcha).

---

## 3. Belt-and-suspenders

- **Weekly export.** On each pilot check-in, grab `temperature_log.csv` from the dashboard (or copy the
  SQLite DB). Cheap off-box backup of the traceability record, and it doubles as your "here's what it
  caught" evidence at conversion.
- **UPS (offered in the pilot).** A small UPS on the **hub PC + router** keeps monitoring alive through
  a brief outage — the one time a cooler is most likely to be in trouble. Optional, but a strong close.
- **Alert path off-box.** Alerts that leave the building (text/email/Slack) need the site's internet;
  keep the on-call phone on cellular so a simultaneous internet + cooler failure still reaches someone.

---

## 4. Prove it (do this before you leave the install)

- [ ] **Reboot the hub PC.** Within ~2 minutes the dashboard is back at `http://localhost:8080` and
      probes reappear on their own — **no one had to open anything.**
- [ ] **Pull a probe's power** and confirm the **silent-sensor / offline alert** fires (this is the
      demo that sells it — "a dark freezer never passes as OK").
- [ ] **Fire a test threshold** (set a limit just past current temp) and confirm the alert lands on the
      real on-call phone, then set it back.
- [ ] Leave a one-line card: *"If the screen is ever blank after a reboot, it restarts itself — give it
      two minutes; still stuck, text me."* plus your support contact.

> If it survives a reboot unattended and the offline alert fires, the install is production-grade. If it
> doesn't come back on its own, fix the auto-start (step 1) before you leave — that gap is exactly what
> makes a pilot fail quietly.
