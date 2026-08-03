# Limited Hardware Warranty

_Last updated: 2026_

This limited warranty is given by **Datum Laboratories LLC**, 1304 Cottonwood Court Northwest,
Kennesaw, GA 30152, USA, and covers the physical **Setpoint** probe hardware you bought
from us or an authorised reseller.

**The hub is software, not hardware.** It is a free application you run on a computer
you already own, so there is no hub device to warrant. If we supplied you a mini-PC as
part of an installation, that computer carries its own manufacturer's warranty, not this one.

## What is covered

For **one (1) year** from the date of delivery, we warrant that the hardware is free
from defects in materials and workmanship under normal indoor use. If a covered defect
appears in that period, we will — at our option and as your sole remedy — **repair the
unit, replace it, or refund the purchase price**.

Covered examples:

- A probe that will not power on, will not connect to Wi-Fi, or never reports a reading
  out of the box.
- A sensor that reads wildly wrong even after calibration against a known reference
  (for example an ice bath).
- A board or connector that fails on its own during normal use.
- Dead-on-arrival units.

Replacement hardware may be new or equivalent-to-new and carries the remainder of the
original warranty period, or 90 days, whichever is longer.

## DIY kits

A kit is a bag of components you assemble and flash yourself, so the warranty is
necessarily narrower:

- **Covered:** a component that is dead, damaged or missing on arrival. Tell us within
  **30 days** of delivery and we will replace it. Test the DS18B20 probe first — a probe
  reading `−127` or blank is the most common bad part and we will simply send another.
- **Not covered:** anything that follows from assembly — reversed polarity, a bridged
  joint, heat damage, a part fitted the wrong way round, or a unit that worked and then
  stopped after rework. We cannot warrant a build we did not make.
- **Not a defect:** the cell is not included, by design (lithium shipping rules). See
  `docs/BOM.md`.

If you would rather not carry that risk, buy an assembled unit once they are available.

## Loaner and pilot units

Equipment installed for an evaluation or pilot **remains our property and is not sold to
you**, so no warranty attaches and nothing here applies. If it fails during the pilot we
replace it or remove it, at no cost, because that is the arrangement. See
`docs/PILOT_OFFER.md`.

## What is not covered

This warranty does **not** cover:

- **Software.** The hub software is provided "as is" under the EULA, and the probe
  firmware "as is" under the MIT License; neither carries a warranty. This document
  covers hardware only.
- **Accidental or physical damage** — drops, crushing, cut cables, insertion of the wrong
  connector, or a cracked enclosure.
- **Liquid immersion or moisture damage** beyond the unit's rating. The stainless probe
  tip is the only part rated for immersion; the electronics are indoor, non-waterproof.
- **Power abuse** — wrong voltage, unregulated supplies, reverse polarity, or damage from
  surges or lightning.
- **Unauthorised modification, repair, or reflashing** with non-provided firmware that
  damages the device, and removed or defaced labels, QR codes or serials.
- **Normal wear** and consumables (for example batteries) and cosmetic marks that do not
  affect function.
- **Misuse or out-of-spec use** — for example placing a standard DS18B20 probe outside its
  rated temperature range, or using it where a certified or redundant measurement device
  is required.
- Loss of data, spoiled goods, or other **consequential losses** — see below.

## Important limits

Setpoint is a **monitoring and temperature-logging aid**, not a certified safety, medical,
food-safety or life-support device, and not a validated critical-control device. Do not
rely on it as the sole safeguard for anything where a missed or wrong reading could cause
loss — medication, high-value stock, or a critical process.

**Accuracy, stated plainly:** the probe is accurate to **±0.5 °C typical between −10 °C
and +85 °C**, uncalibrated. **Below −10 °C — which includes a typical −18 °C freezer — it
is ±2 °C.** That is enough to tell you a freezer has failed, which is what an alarm is
for. It is not precise enough to serve as a calibrated record at a frozen-storage
threshold, and we do not offer it as one.

To the fullest extent permitted by law, our total liability under this warranty is limited
to the amount you paid for the hardware, and we are not liable for indirect, incidental or
consequential damages such as spoiled inventory. Some jurisdictions do not allow certain
exclusions, so parts of this may not apply to you.

This warranty gives you specific legal rights. You may also have **other rights under your
local consumer-protection law**, and nothing here limits any right that cannot legally be
waived.

## How to make a claim

1. **Contact support** at **support@datumlaboratories.com** within the warranty period. Please include
   the information listed in `SUPPORT.md` — your order number or proof of purchase, the
   probe ID (for example `Setpoint-9A3F2C`), the firmware version, and a clear description
   of the fault.
2. **Basic troubleshooting.** We may ask you to try a few quick steps — re-seat the probe,
   re-provision, check power — to confirm it is a hardware fault and not a setup issue.
3. **Return authorisation.** If it is a covered defect we will issue a return
   authorisation and instructions. Please do not ship anything back before you receive one.
4. **Resolution.** Once we receive and inspect the unit we repair, replace or refund as
   described above. If a returned unit shows no defect, or an excluded cause, we will tell
   you before proceeding.

Proof of purchase is required. Shipping arrangements for warranty returns are handled case
by case per the instructions we send.
