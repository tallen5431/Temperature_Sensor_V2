# Setpoint Maker Kit — Pre-Order Copy (paste-ready)

> Ready-to-paste copy for the **founding-batch pre-order** — your fastest clean dollar
> ([`ACTION_PLAN.md`](ACTION_PLAN.md) priority #1). Everything here is worded to stay **FTC
> mail-order-clean** and to match the honest-specs posture in [`LISTING.md`](LISTING.md) /
> [`WARRANTY.md`](WARRANTY.md). Fill the `[BRACKETED]` bits. **Not legal advice — have a
> small-business attorney sanity-check the refund wording before you publish.**

---

## 0. The model: lead with a small refundable deposit

Boards are inbound and the flashing toolchain is documented-but-not-yet-hardware-verified, so **don't
take full pre-pay from strangers yet.** Lead with a **$15 fully-refundable deposit** that locks a
founding price. It de-risks both sides, keeps you FTC-clean if the build slips a week, and lowers the
odds a new payment processor freezes the funds.

| Option | Price | Who it's for | Notes |
|---|---|---|---|
| **Founding deposit** ⭐ | **$15** (refundable) | Everyone at launch | Applies to the $39 kit → $24 balance at ship |
| Full pre-pay | $39 | Buyers happy to wait the honest window | Full 30-day FTC clock attaches immediately |

Cap it at **25** so one buyer can't clear the batch, and so "founding batch" stays true.

---

## 1. Stripe Payment Link — field by field

Create it under the **Datum Labs LLC** Stripe account (business bank + EIN attached).

- **Product name:** `Setpoint Maker Kit — Founding Batch (pre-order)`
- **Price:** `$15.00` one-time · label it **"Refundable founding deposit"**
- **Image:** the hero-unit or parts flat-lay photo (add once you've shot it)
- **Quantity:** let customers adjust (a buyer with 2 probes pays 2 deposits) · **limit total to 25**
- **Collect:** ✅ email · ✅ shipping address · ✅ phone (optional)
- **Custom fields:**
  - `How many probes? (1 / 2 / 4)` — dropdown
  - `Where will you use it? (homelab / restaurant / greenhouse / other)` — optional, free text
- **After payment → custom confirmation page** with the message in §3.
- **Description (shows on the checkout page):** paste §2.

---

## 2. Checkout description (paste into the Stripe "description")

```
A wireless temperature probe that reports to a free app on your OWN computer — no cloud,
no account, no subscription. This is the FOUNDING-BATCH pre-order deposit.

Your $15 deposit is fully refundable, locks the $39 founding price (you pay the $24
balance only when your kit ships), and reserves one of the first 25 kits.

What you'll get (ships ~4 weeks from order):
• The Setpoint carrier board + a pre-flashed ESP32-C3 (no software to install on the probe)
• A waterproof DS18B20 temperature probe (1 m)
• Pull-up resistor, charge board, switch, headers — you assemble it (fun ~20-min solder)
• A printed quick-start card: power on → join the probe's Wi-Fi → watch it appear

Honest specs (so there are no surprises):
• Accuracy ±0.5 °C typical, uncalibrated (add a per-probe offset in the app)
• 2.4 GHz Wi-Fi only · needs a computer you leave on to run the free hub
• Lithium cell NOT included (ship rules) — use any protected 18650
• A loss-prevention / logging aid — NOT a certified, NIST-traceable, or HACCP/health-code
  instrument, and monitoring stops during a power outage

Setpoint, by Datum Labs.
```

---

## 3. Confirmation / thank-you page (paste into Stripe "after payment")

```
You're in — thank you for backing the founding batch of Setpoint.

Your $15 deposit is refundable any time before your kit ships. We're aiming to ship in
about 4 weeks; if anything slips, we'll email you and you can cancel for a full refund,
no questions asked. When your kit is ready we'll email a link to pay the $24 balance and
confirm your address.

Questions any time: [support@yourdomain]
— [Your name], Datum Labs
```

---

## 4. Confirmation email (Stripe sends a receipt; send this too, or set as the receipt note)

```
Subject: You're a Setpoint founding backer 🎉

Hi [first name],

Thanks for reserving one of the first 25 Setpoint Maker Kits. Here's the deal, in plain terms:

• You paid a $15 deposit. It's fully refundable until your kit ships.
• It locks the $39 founding price — you'll pay the remaining $24 only when we ship.
• Target ship window: ~4 weeks ([target month]). If we slip, we email you and you can
  cancel for a full refund.

Your kit is the solder-it-yourself Maker tier: a pre-flashed probe + a waterproof sensor +
the parts, and a free app you run on your own PC (no cloud, no subscription). Full honest
specs are on the product page.

I build these by hand and I'll keep you posted as the batch comes together.

— [Your name]
Datum Labs · [support@yourdomain] · [repo / site link]
```

---

## 5. Landing-page "Reserve a kit" block (paste into your site)

```
## Reserve a Setpoint kit — founding batch

A wireless temperature probe that answers to YOU, not a cloud. Runs on a free app on your
own PC. Track a fridge, freezer, server rack, or greenhouse and get an alert the moment it
drifts — no account, no subscription, ever.

[ Reserve my kit — $15 refundable deposit ]   ← links to the Stripe payment link

Only 25 in the founding batch · ships ~4 weeks · $15 locks the $39 price.
Not ready to commit? [ Email me when it's for sale ] → (email capture)
```

**Log every reservation** (email · probe count · deposit y/n) to a CSV — that list is your
launch-day customer base and your restaurant-pilot lead list.

---

## 6. The one-line launch announcement (post once, honestly)

**README banner / site:**
```
🎯 Setpoint founding batch is open — reserve a DIY kit for a $15 refundable deposit (25 only).
```

**r/homelab · r/selfhosted (lead with the differentiator, not "temperature sensor"):**
```
I built a local-first Wi-Fi temp monitor — flash it from your browser, runs on your own PC,
no cloud/account/subscription. Opening a small founding batch of DIY kits ($15 refundable
deposit locks $39). Free hub software + firmware are open; happy to answer anything.
```

**Restaurant contact (text, not email — lead with loss, not tech):**
```
Hey [name] — finally launching the walk-in monitor I mentioned. It texts you the second a
cooler starts drifting overnight, before you open the door to a dead compressor. I'll set
it up in your kitchen free for 30 days, no strings — want me to bring one by this week?
```

---

## 7. FTC mail-order checklist (the rules behind the wording above)

- [ ] **State an honest ship window** ("~4 weeks"). If you don't, the law defaults to **30 days**.
- [ ] **If you'll miss the window,** email the buyer, give a revised date, and offer **cancel for a
      full refund**. Silence is the violation, not a delay.
- [ ] **Refund promptly** to the original payment method when asked (deposits are refundable by design).
- [ ] **Identify the seller** (Datum Labs LLC) and a **working support email** — not a placeholder.
- [ ] **Link real Returns + Warranty** ([`RETURNS.md`](RETURNS.md) / [`WARRANTY.md`](WARRANTY.md), once
      you've swapped in the LLC name + real support URL).
- [ ] **Sales tax:** enable Stripe Tax for your home state (direct sales are yours to remit; on Tindie
      the marketplace remits for you).
- [ ] **Don't overstate:** keep "±0.5 °C typical, uncalibrated" and the "not a certified/HACCP
      instrument" line anywhere you describe accuracy. Never imply a certification you don't hold.

> Prerequisite (see [`MATERIALS_AND_NEXT_STEPS.md`](MATERIALS_AND_NEXT_STEPS.md) Gate 0–1): LLC + EIN +
> business bank + a real domain/support email must exist **before** the link goes live.
