# Browser-based flashing (ESP Web Tools)

This folder is a self-contained web page that flashes the **ThermaProbe** firmware
onto an ESP32 straight from a desktop browser — no Arduino IDE, no toolchain. It's
the **lowest-friction on-ramp for hobbyists / kit buyers**: they open a link, click
one button, and the probe is ready to set up.

```
flash/
├── index.html               the flashing page (ESP Web Tools install button)
├── manifest.json            firmware descriptor ESP Web Tools reads
├── build_merged_bin.sh      builds the single merged .bin the page flashes
└── thermaprobe-esp32.merged.bin   (generated — NOT committed, .gitignored)
```

## How it works

`index.html` loads the [ESP Web Tools](https://esphome.github.io/esp-web-tools/)
web component, which uses the browser's **Web Serial** API to talk to the ESP32
over USB. `manifest.json` tells it which binary to flash (a single merged image at
offset `0x0`).

**Browser support:** Web Serial works in **Chrome, Edge, and Opera on desktop**,
over **HTTPS** (or `http://localhost`). Safari, Firefox, and mobile browsers can't
flash — the page shows a note and points those users to manual flashing.

## Publishing it (one-time)

1. **Generate the firmware binary** (you need `arduino-cli` + the esp32 core, and
   `esptool`):
   ```bash
   arduino-cli core install esp32:esp32
   pip install esptool
   ./flash/build_merged_bin.sh          # writes flash/thermaprobe-esp32.merged.bin
   ```
   Keep `manifest.json`'s `version` in sync with `FW_VERSION`
   (`esp32_temp_probe/esp32_temp_probe.ino`).

2. **Host the `flash/` folder over HTTPS.** The easiest free option is **GitHub
   Pages**: enable Pages for this repo (Settings → Pages → deploy from the default
   branch), then the page is served at
   `https://<you>.github.io/<repo>/flash/`. Because the binary is `.gitignored`,
   either commit it to the Pages branch specifically or publish it as a release
   asset and point `manifest.json` at that URL.

3. **Link it** from your product listing, the unit label/QR, and the README.

> Like every firmware step here, the produced binary **must be validated on real
> ESP32 hardware** (build → flash → QC per [`../docs/QC_CHECKLIST.md`](../docs/QC_CHECKLIST.md))
> before you ship it. Nothing in `flash/` has been run on hardware.

## Manual flashing (fallback / power users)

Anyone who can't (or would rather not) use the browser can flash with
`arduino-cli`/`esptool` directly — see [`../firmware/README.md`](../firmware/README.md).
The maker's assembly-line path stays [`../firmware/factory_flash.py`](../firmware/factory_flash.py).
