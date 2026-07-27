# Income Streams Beyond Setpoint Hardware

*Companion to [`ACTION_PLAN.md`](ACTION_PLAN.md). That doc monetizes **Setpoint**; this one monetizes
**you** — the skills already listed on `/about` — through paths that need no boards, no FCC SDoC,
and no inventory. Deliberately non-overlapping: nothing here repeats the pre-order / pilot / Tindie
stack.*

> **The framing that matters:** Setpoint is a *product* bet — high ceiling, long fuse, gated on
> parts and certification. Everything below is a *service or digital* bet — lower ceiling per unit,
> but the fuse is days, not months. Run the service tier to pay your bills and fund the product
> tier. That's the normal order for a one-person hardware shop, not a retreat from it.
>
> Dollar figures are **observed market ranges to validate**, not promises — same convention as
> [`GO_TO_MARKET.md`](GO_TO_MARKET.md). Treat them as ceilings to test, and expect your first
> engagement to land at the bottom of the range.

---

## The honest ranking

Speed-to-first-dollar, given what you can do *today* with equipment you already own:

| # | Stream | First $ | Rate / unit | Effort to start |
|---|--------|---------|-------------|-----------------|
| 1 | Local smart-home & network installs | 3–10 days | $75–125/hr + parts | Low |
| 2 | Freelance firmware / PCB contracting | 1–3 weeks | $60–150/hr | Low |
| 3 | Edge-vision (Jetson) contracting | 2–6 weeks | $100–200/hr | Low, but slower funnel |
| 4 | Design-for-print CAD service | 1–2 weeks | $75–400/model | Low |
| 5 | Enclosure design for other hardware makers | 2–4 weeks | $400–2,500/project | Medium |
| 6 | The hardware-startup guide (you already wrote it) | 1–3 weeks | $39–99 | Medium, one-time |
| 7 | Setpoint Pro / commercial license | 2–5 weeks | $99–299 + recurring | Medium |
| 8 | Niche printed product line | 3–8 weeks | $12–60/item | Medium, compounds |
| 9 | Local B2B monitoring installs (beyond restaurants) | 3–8 weeks | $300–800 + $25–50/mo | Medium |
| 10 | Model royalties + content | 2–6 months | $50–500/mo eventually | Low effort, slow |

**If you only pick three:** #1 and #2 for cash flow, #5 because it's the one where "making things
for people" and your actual edge overlap perfectly. #6 is the highest-leverage weekend you'll spend.

---

## Tier A — cash in days, zero inventory

### 1. Local smart-home, network & homelab installs ⭐ fastest realistic dollar

Home Assistant setups, Wi-Fi/mesh rework, NAS + backup, camera systems, rack cleanups. No
certification required, no capital, and demand is steady in every metro. You are dramatically
overqualified, which is exactly why you'll close: the competition is a general handyman or a
$200/hr MSP with a two-week lead time.

- **First dollar:** 3–10 days. **Per job:** $75–125/hr, most jobs 2–5 hours, plus parts at cost+20%.
- **Why it fits:** it's your Setpoint install motion (hub on a PC, sensors on a LAN, alerts that
  work) sold as labor instead of hardware. Every job is also a warm lead for a Setpoint pilot.
- **First 3 actions:**
  - [ ] Post a services listing on Nextdoor + Facebook Marketplace + local subreddit: *"Home
        Assistant / smart home setup that doesn't depend on a cloud account — local engineer."*
  - [ ] Add a fourth card to `site/services.html` for local install work, with a service-area line.
  - [ ] Set up Square or Stripe Tap-to-Pay so you can take payment at the door.
- **Gotcha:** you're entering people's homes — get a general-liability policy bound before the
  first job (you're already pulling CGL quotes for the pilots in [`START_HERE.md`](../START_HERE.md);
  one policy covers both). Never touch line-voltage wiring without an electrician.

### 2. Freelance firmware & PCB contracting

ESP32/embedded C++ and KiCad schematic + layout are two of the most consistently in-demand
freelance skills, and you have shipped proof of both — which is the thing 90% of applicants
can't show. Setpoint is your portfolio piece; the field-test writeup is your credibility.

- **First dollar:** 1–3 weeks. **Rate:** $60–150/hr; fixed-scope firmware jobs commonly $800–5,000.
- **Where the work is:** Upwork and Contra for volume; r/embedded and r/PrintedCircuitBoard "hiring"
  threads; Hacker News *Who Wants to Be Hired* (monthly, free, high signal); the Tindie/Crowd Supply
  seller community, which is full of people who can design a board but not write the firmware.
- **The positioning that wins:** don't list skills — lead with *"I took an ESP32 product from
  schematic to shipping kit, including the offline buffering, the deep-sleep power budget, the
  browser flasher, and the FCC path. Here's the repo."* That single sentence outranks a skills list.
- **A sharper wedge — cloud-orphan rescue:** IoT vendors keep shutting down cloud back ends and
  bricking devices people paid for. "I make your orphaned devices work locally again" is a real,
  searchable pain, it's *literally your product thesis*, and almost nobody advertises it.
- **First 3 actions:**
  - [ ] Upwork + Contra profiles, headline = the sentence above, portfolio = Setpoint + the field test.
  - [ ] Write one 800-word post: *"What shipping an ESP32 product actually costs"* — post to
        r/embedded and Hacker News. It's a lead magnet and a credibility artifact at once.
  - [ ] Answer the next HN *Who Wants to Be Hired* thread and 3 relevant r/embedded job posts.
- **Gotcha:** on the marketplaces, price at the top of the range and take fewer jobs. Racing to the
  bottom against offshore shops is unwinnable and it poisons your rate anchor for later clients.

### 3. Embedded computer vision / Jetson contracting — your scarcest skill

This is the item on your `/about` page with the least competition and the highest rate. Plenty of
people do "computer vision" in a notebook; very few have driven live low-light camera vision to a
head-mounted display on a Jetson, with the power and mechanical design to make it wearable. That
combination is genuinely rare.

- **First dollar:** 2–6 weeks (longer funnel, larger contracts). **Rate:** $100–200/hr; project
  engagements $5k–40k.
- **Who buys:** agtech (in-field crop/livestock vision), industrial inspection, wildlife and
  conservation research, security integrators, robotics startups, AR/VR hardware shops, and any
  company that prototyped in the cloud and now needs it to run on a device at the edge.
- **First 3 actions:**
  - [ ] **Make the Jetson repo public and presentable** — right now `/services` says *"code on
        GitHub"* and links to your profile root. A specific, documented repo with a photo of the
        rig and a "what this does / how it's built" README is the entire sale for this niche.
  - [ ] Write the build up the way you wrote the battery field test: problem, build, measured
        result, honest limits. Post it to r/computervision and the NVIDIA developer forums.
  - [ ] Split "Vision & AR/VR" on `/services` into its own landing page with that writeup embedded.
- **Gotcha — read this one:** night-vision and thermal imaging brush against **US export control**
  (ITAR/EAR). A Jetson with a COTS low-light CMOS sensor is very likely ordinary commercial gear,
  but image-intensifier tubes, certain IR/thermal sensitivities, and defense-adjacent or overseas
  clients change the analysis. Before you take a defense, law-enforcement, or non-US client for
  night-vision work, spend an hour with an export-controls attorney. Do not skip this because the
  first project is small.

### 4. Design-for-print CAD service (not a print farm)

The money in 3D printing is in the **CAD**, not the extrusion. "Send me an STL and I'll print it"
competes against Craftcloud, JLC3DP and PCBWay on price and loses. "I'll model the part you can't
find" has no such competition, and your two printers become the proofing step rather than the product.

- **First dollar:** 1–2 weeks. **Per model:** $75–400; a functional part with a couple of revisions
  commonly $150–300.
- **The offer:** "Send me a photo, a sketch, or the broken part with a ruler next to it — you get a
  printable, tested part plus the STEP file." Test-printing before you deliver is your differentiator;
  most online CAD sellers hand over a model that has never touched a printer.
- **First 3 actions:**
  - [ ] Rewrite the 3D-printing card on `/services` — lead with **design**, list printing as the
        fulfillment step. It currently reads "send an STL," which sells the commodity half.
  - [ ] List a fixed-price gig: *"Custom functional part designed & test-printed — $149"*.
  - [ ] Model and print three demo parts (a bracket, an enclosure, a discontinued knob) and photograph
        them next to their sources. That triptych is the whole portfolio you need.
- **Gotcha:** quote in *revisions included* (say, two), not in hours. Unbounded revision cycles are
  what make this work unprofitable.

---

## Tier B — productize what you already have

### 5. Enclosure & mechanical design for other hardware makers ⭐ best strategic fit

Hundreds of small hardware sellers (Tindie, Crowd Supply, Kickstarter, one-person IoT shops) have a
working board and a terrible box. They can't do mechanical design, and a mechanical contractor who
also understands antenna keep-outs, thermal budgets, connector stack-ups, and DFM for print-vs-mold
is genuinely hard to find. You are that person, and you can *talk to them as a peer* — you've
shipped the same thing they're shipping.

- **First dollar:** 2–4 weeks. **Per project:** $400–2,500; retainer relationships are common once
  a client ships rev 2.
- **The pitch:** *"You have a PCB. I'll give you an enclosure that fits it, prints or molds cleanly,
  passes a drop test, and doesn't detune your antenna — plus the STEP files, so you're never locked
  to me."* That last clause is already your `/about` philosophy; it closes deals.
- **First 3 actions:**
  - [ ] Photograph your own Setpoint enclosure work — that IS the portfolio, and it's already built.
  - [ ] DM 15 active Tindie/Crowd Supply sellers whose product photos show a bare board or a generic
        project box. Personalized, one specific observation each, no template blast.
  - [ ] Publish a fixed-price ladder: $450 simple enclosure / $1,200 enclosure + mounts + DFM review.
- **Gotcha:** insist on the board's STEP file or a dimensioned drawing before quoting. "I'll measure
  it from photos" is how you eat two free revisions.

### 6. Sell the hardware-startup playbook you've already written

You have **4,200+ lines** across `docs/` — BOM, assembly, QC checklist with an ice-bath procedure,
FCC/CE compliance path, label template, Tindie listing copy, warranty, returns, EULA, pre-order
mechanics, launch runbook, go-to-market research. That is not a folder of notes. That is a product
that thousands of makers stall out for lack of, and the marginal cost of selling it is zero.

- **First dollar:** 1–3 weeks. **Per sale:** $39–99. 100 sales = $4,000–9,900 for work already done.
- **The product:** *"From ESP32 breadboard to a product you can legally sell"* — the doc set as a
  clean PDF/web bundle, with the real templates as editable files. Price the templates, not the prose;
  the FCC path, QC checklist, and paperwork set are what people pay for.
- **Why it sells:** every maker forum has the same recurring question — *"I built a thing, how do I
  actually sell it? Do I need FCC?"* — and the answers are scattered and wrong. You solved it in
  public, on a real product, and you can point at the product.
- **First 3 actions:**
  - [ ] Pick the ~12 docs that generalize beyond Setpoint; strip Setpoint-specific values into
        `[BRACKETS]` the way [`PILOT_OFFER.md`](PILOT_OFFER.md) already does.
  - [ ] Gumroad listing at $49, with `COMPLIANCE.md` free as the sample chapter — it's the section
        that proves you actually know the thing.
  - [ ] Launch it on the back of the r/embedded post from stream #2, not as a standalone ad.
- **Gotcha:** add a plain "this is not legal advice" line — you already carry one in
  [`README.md`](../README.md), keep it. And don't include anything you'd want kept proprietary about
  the rev-2 design.

### 7. Setpoint Pro — software-only, no FCC gate, recurring

The hub is free and stays free; that's the brand. But **commercial** users have needs hobbyists
don't, and software has no bill of materials, no lead time, and no certification gate.

- **First dollar:** 2–5 weeks. **Per sale:** $99–299 one-time or $9–29/mo.
- **What justifies the price:** scheduled PDF/Excel report packs for a records binder, multi-site
  rollups, SMS escalation chains, priority support with a response-time commitment, and a commercial
  use license. You already ship the hard parts — the audit log, Excel export, and alert state machine.
- **First 3 actions:**
  - [ ] Define the free/Pro line publicly and honestly; never remove something free users already have.
  - [ ] Build the scheduled-report generator first — it's the single most requested commercial feature
        in this category and it's mostly assembly of code you have.
  - [ ] Gumroad license key + a `pro` config block; sell it to your pilot restaurants at conversion.
- **Gotcha:** keep positioning it as **loss prevention**, matching `PILOT_OFFER.md`. The moment you
  market it as HACCP or health-code *compliance*, you inherit a regulatory burden and need
  NIST-traceable calibration. Same reason to decline pharmacy and vaccine-storage work for now.

### 8. A niche printed product line you own

Not job-shop printing — a small catalogue of your own designs, printed on demand. This is where the
two printers finally earn instead of idle.

- **First dollar:** 3–8 weeks. **Per item:** $12–60, 60–80% margin. **Compounds** — every listing
  keeps selling.
- **Niches that actually move, ranked for you:**
  1. **Homelab & rack accessories** — Pi/mini-PC/NAS mounts, 10" rack shelves, DIN clips, cable
     combs, blanking plates. *This is your existing audience.* You're already posting to r/homelab.
  2. **Setpoint accessories** — probe mounts, walk-in door brackets, magnetic cases, cable strain
     reliefs. Sell as kit add-ons at near-zero acquisition cost, and they lift kit AOV.
  3. **Discontinued replacement parts** — appliance knobs, dishwasher rack clips, RV/boat trim,
     stroller clips. Highest margin in printing because there is *no competing supply* and buyers
     search for it with wallet in hand.
- **First 3 actions:**
  - [ ] Design 5 homelab parts; list on Etsy + as Setpoint add-ons; post free versions to Printables.
  - [ ] Photograph every part *in situ*, not on a print bed. In-use photos are the conversion driver.
  - [ ] Track print time per item — anything under $8/hr of machine time gets cut from the catalogue.
- **Gotcha:** don't buy more printers to scale this. Two printers plus good designs beats six printers
  with commodity listings, and the moment you need capacity you rent it from a print service.

---

## Tier C — local B2B, slower to start, best retention

### 9. Monitoring installs beyond restaurants

Same install motion as the restaurant pilot, different verticals — and several have money and no
incumbent. Once installed, the relationship is sticky and the service fee is close to pure margin.

- **Best targets:** craft breweries and cideries (fermentation temps, and they *love* local vendors),
  butchers and delis, florists, cheese and charcuterie makers, kombucha and hot-sauce producers,
  small greenhouses and nurseries, church and community-center kitchens, server closets at small
  law/dental/accounting offices, and museum or gallery storage.
- **The multiplier: subcontract to local MSPs.** Every small MSP has client racks in unmonitored
  closets and no time to solve it. One MSP relationship = 5–20 sites through a single conversation.
- **Money:** $300–800 install + $25–50/mo per site for monitoring, alert tuning, and check-ins.
- **First 3 actions:**
  - [ ] List every brewery, MSP, and specialty food producer within 30 miles. Aim for 20 names.
  - [ ] Adapt [`PILOT_OFFER.md`](PILOT_OFFER.md) per vertical — swap the walk-in loss math for
        fermentation batch loss or rack downtime.
  - [ ] Walk into three in person. This vertical does not answer cold email; it answers a person.
- **Gotcha:** same FCC discipline as the restaurant pilots — loaner units, and you bill labor plus an
  already-certified mini-PC, never an assembled rev-1 radio. Bind insurance before the first
  commercial install; have the COI and W-9 ready because procurement will ask.

### 10. Local jigs, fixtures & short-run parts for small manufacturers

Machine shops, cabinet makers, sign shops, and small assemblers all need one-off fixtures, soft jaws,
gauges, and guards. They pay quickly, they reorder, and they don't shop around — they just want the
problem gone. Turnaround is your entire competitive advantage over an online service.

- **Money:** $80–400 per fixture, frequently repeat. **First dollar:** 2–4 weeks.
- **First action:** visit three local shops with two printed sample parts in hand and one question:
  *"What do you keep breaking, or keep making out of plywood and tape?"* The answer is the order.

---

## Tier D — slow compounding (start now, ignore until it works)

- **Model royalties** — MakerWorld's reward program, Printables contests, Cults3D. Realistically
  $50–500/mo after months of consistent uploads, but each upload is a permanent asset and a
  top-of-funnel ad for stream #4.
- **Build-in-public content** — you write unusually well (the field-test report and the honesty about
  what it does and doesn't establish are the proof). A blog or YouTube on ESP32 product work and the
  night-vision rig will not pay directly for a year, but it is the single best lead source for
  streams #2, #3, #5 and #6, all of which are high-ticket.
- **Teaching** — an ESP32 or 3D-printing workshop at a local makerspace or community college. $200–600
  per session, and every attendee is a warm lead.

---

## What I'd actually do in the next 14 days

Three parallel tracks, roughly 20 hours total:

**Days 1–3 — turn on the cash tap.**
- [ ] Post the local smart-home/network install listing (Nextdoor + Marketplace + local subreddit).
- [ ] Upwork and Contra profiles live, headlined with the Setpoint shipping story.
- [ ] One fixed-price CAD gig listed.

**Days 4–9 — fix the site so it sells the right things.**
- [ ] Make the Jetson repo public with a real README and photos. This is the highest-value hour on
      the list — the rarest skill on your site currently links to a profile root.
- [ ] Rewrite the 3D-printing card to lead with **design**, not printing.
- [ ] Add a local-install card and a service-area line to `/services`.
- [ ] Add a "recent work" strip to `/about` with the three demo prints and the enclosure photos.

**Days 10–14 — ship one digital product.**
- [ ] Bracket-ify the 12 generalizable docs and put the playbook on Gumroad at $49.
- [ ] Write the "what shipping an ESP32 product actually costs" post; launch the playbook from it.
- [ ] DM 15 Tindie/Crowd Supply sellers about enclosure design.

**The trap to avoid:** all of these are real, and doing all ten is how you earn from none. Pick
three, give them 60 days, kill what doesn't move. Your product instinct is already good — the
constraint is attention, not ideas.

---

## Cross-cutting gotchas

- **Insurance before any commercial or in-home work.** One general-liability policy covers the
  installs, the pilots, and the local service work. Bind it before the first job, not after the
  first incident.
- **Set aside ~30% of every service dollar for self-employment tax.** Freelance income has no
  withholding; quarterly estimates start the quarter you earn.
- **Everything invoices through the LLC** once [`STARTUP_CHECKLIST.md`](STARTUP_CHECKLIST.md) is done
  — that's what makes the liability shield and the clean books real.
- **Stay off regulated ground until you're ready for it:** no medical, pharmacy, vaccine-storage, or
  health-code *compliance* claims without NIST-traceable calibration and legal review. Loss
  prevention is the honest, unregulated, and still very sellable framing.
- **Export controls on night-vision work** — see stream #3. Get advice before defense-adjacent or
  non-US clients.
- **Not legal, tax, or insurance advice.** Confirm specifics with an attorney, accountant, and broker
  before binding money — same caveat that opens [`START_HERE.md`](../START_HERE.md).
