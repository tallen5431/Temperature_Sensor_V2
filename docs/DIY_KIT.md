# Setpoint — DIY Kit Playbook (sell rev-1 boards now, zero assembly for you)

> The kit is your **fastest, lowest-risk product**: you bag parts, the buyer assembles, so there's no
> assembly labor and (because the buyer builds the radio) it sidesteps finished-product FCC. This doc
> is about one thing: **removing every reason a buyer hesitates or gives up.** Pairs with
> [`TINDIE_LISTING.md`](TINDIE_LISTING.md) (listing copy) and [`PRODUCT_ROADMAP.md`](PRODUCT_ROADMAP.md).
>
> **Two versions to list** (see [`VERSIONS.md`](VERSIONS.md)): the **Portable** kit (battery + TP4056 +
> switch — a movable tool you carry to any reading) and a cheaper **Fixed** kit (USB, no battery —
> always-on for a rack, greenhouse, or walk-in). Same board, probe, and firmware; they're just two power
> options on the listing. This is orthogonal to the Maker/Plug-Together solder tiers below.

---

## The core idea: sell an *experience that can't fail*, not a bag of parts

A kit lives or dies on two fears: **"I'll mess up the soldering"** and **"I'll get stuck flashing
firmware."** Kill both and the kit sells itself. Everything below is aimed at those two fears.

---

## Kill fear #1 — flashing. **Pre-flash every board before it ships.**

Flashing is **not** assembly, so pre-flashing the ESP32-C3 is FCC-safe *and* it's the single biggest
friction remover. Ship each board already running the firmware, so the buyer **never opens a
toolchain**. Their whole "software" step becomes: power on → join the `Setpoint-XXXXXX` Wi-Fi →
open the dashboard. That's your product's magic moment (auto-provision + onboarding already handle it).

- Belt-and-suspenders: **also** print the QR to your **browser-flash page** (ESP Web Tools) on the
  card, so if they ever need to re-flash, it's one click from Chrome — no Arduino, no drivers hunt.
- Put the firmware **version + probe serial** on the board's label so support is traceable.

## Kill fear #2 — soldering. **Offer a no-iron path.**

Sell it in two tiers so nobody is scared off by a soldering iron:

| Tier | What you do | What the buyer does | Price |
|---|---|---|---|
| **Maker Kit** | Bag loose parts (board + SuperMini + probe + resistor + TP4056 + switch + headers) | Solders it (fun for the maker crowd) | **~$39** |
| **Plug-Together Kit** | Pre-solder the **female headers + screw terminal for the probe** onto the board | Plugs the SuperMini + TP4056 into headers, screws the probe leads in, snaps in the cell — **no iron** | **~$49** |

> Keep the **final radio + power assembly with the buyer** (they seat the module and power it up) so
> it stays a genuine kit. Pre-soldering passive headers is fine; if you ever scale kits, confirm the
> current FCC kit rules with a consultant.

The Plug-Together tier roughly **doubles your reachable audience** — it reaches the "I want it but I
don't solder" buyer — for a few minutes of header soldering you do in a batch.

---

## What's in the bag (make it feel complete and premium)

- ✅ Rev-1 carrier PCB (**pre-flashed** SuperMini seated or bagged with it).
- ✅ DS18B20 waterproof probe (1 m).
- ✅ 4.7 kΩ pull-up resistor (**pre-bent to pitch**) + headers / screw terminal.
- ✅ TP4056 charger + 18650 holder. **State clearly whether the 18650 cell is included** — shipping
  lithium cells has carrier rules and added cost; many kits ship **cell-not-included** with a
  "any protected 18650" note.
- ✅ Slide switch.
- ✅ A **printed quick-start card**: 5 numbered steps with pictures, the **setup QR**, the
  **browser-flash QR**, and links to `docs/ASSEMBLY.md` + `docs/USER_MANUAL.md`. A ready-to-print
  A5 template (branded **Setpoint, by Datum Labs**) lives at
  [`kit-quickstart-card.html`](kit-quickstart-card.html) — open it in a browser and Print to PDF.
- ✅ A **1-line "known-good" test**: "Power on → the LED blinks → it appears on your dashboard within
  a minute." A buyer who can self-verify success won't open a support ticket.
- ✅ A short **lithium-safety line** (if the kit involves an 18650): *"Use a protected cell, observe
  polarity, never short the terminals, charge only via the TP4056."* Cheap insurance against a bad
  outcome and a liability claim.
- Nice touches that punch above $39: an anti-static bag, labeled parts baggies, a strip of heatshrink,
  and a sticker. Presentation is most of the perceived value at this price.

---

## Make the instructions foolproof (this is where kits are won or lost)

- **Illustrated card + a 60-second assembly GIF/video.** Every step numbered; one action per step.
- **Name parts by what they look like**, not just designators ("the small blue board = the charger").
- **A short troubleshooting box** that pre-answers the top 3 tickets:
  - Probe reads **−127 / blank** → the DS18B20 pull-up isn't seated. 
  - **Not joining Wi-Fi** → it's **2.4 GHz only**; pick a 2.4 GHz network.
  - **Nothing on the dashboard** → confirm the hub PC and probe are on the same network.
- Point deeper questions to `docs/USER_MANUAL.md` so the card stays short.

---

## Make the listing convert (attractiveness)

- **Lead the title/first line with the differentiator**, not "temperature sensor":
  *"Flash it from your browser · runs on your own PC · no cloud, no subscription."*
- **Photos win Tindie.** Shoot: the built unit (hero), the parts flat-lay, the dashboard on a laptop,
  and a probe-in-context (fridge/rack). One built unit — which you're making for pilots anyway — covers it.
- **Honest specs** (±0.5 °C typical uncalibrated; 2.4 GHz; needs an always-on PC) — technical buyers
  trust honesty and it prevents returns. (Copy is in [`TINDIE_LISTING.md`](TINDIE_LISTING.md).)
- **Anchor the price:** ~$39 kit vs. a $149 Temp Stick — and the hub software is **free forever**.
- **Upsell the architecture:** one hub → many probes. Offer a **2-probe** or **4-probe** kit; per-probe
  price drops and your bagging time barely changes.
- **Social proof:** link the GitHub repo, mention build-in-public, gather early reviews.

---

## The ops (keep it small and cheap)

- **Buy parts in 10s**, bag by hand — near-zero capital, no inventory risk beyond parts.
- **Channel:** Tindie (maker audience, kits explicitly welcome, ~5% fee, <48 h approval). Keep your
  own site for the free software + waitlist, not a competing listing (Tindie is web-exclusive per SKU).
- **Handling time:** set an honest 3–5 business days for hand-bagged batches.
- **Test every probe before bagging** — power the pre-flashed board, confirm it reads a sane room
  temperature (not −127/blank). A dead DS18B20 is the most likely bad part and a guaranteed return;
  catching it at the bench costs seconds.
- **Track each kit's probe serial** in your batch log (`docs/LABEL_TEMPLATE.md` style) so a support
  request maps to a known unit.
- **Returns/support:** the pre-flash + foolproof card + honest specs are your best defense against both.

---

## Why the kit is the right first move

- **$0 assembly labor, $0 FCC gate, near-$0 capital** — the cheapest way to get real paying customers.
- **It validates the same demand** as the assembled unit, so what you learn transfers directly to the
  rev-2 assembled SKU.
- **Your software makes the payoff instant** — pre-flashed + auto-provision means the buyer's first
  experience is "it just showed up on my dashboard," which is exactly what earns a review.

**Start here, pre-flash everything, offer the no-solder tier, and let the browser-flash page + your
onboarding do the selling.**
