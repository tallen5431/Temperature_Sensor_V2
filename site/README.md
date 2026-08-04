# site/ — datumlaboratories.com

Source of record for the **public site at `datumlaboratories.com`**. It is no longer a single
landing page; the pages below each serve a different visitor, and which offer they carry is
deliberate.

| Page | Serves | Primary call to action |
|---|---|---|
| `index.html` | Product overview, all audiences | DIY kit ($39, Tindie) |
| `pilot.html` | **Restaurant owners — the highest-value offer available today** | Book the free 30-day loaner pilot |
| `walk-in-cooler.html` | Restaurants searching for cooler/freezer monitoring | Book the pilot (kit demoted to secondary) |
| `freezer-alarm.html` | Consumers/prosumers searching freezer & fridge terms | DIY kit |
| `field-test.html` | Sceptical technical buyers — trust asset | Read, then kit |
| `roi-calculator.html` | Kitchen operators pricing the risk | Walk-in cooler / pilot |
| `services.html` | Contracting clients | Start a project |
| `replacement-parts.html` | Repair customers (its own funnel, with quote form) | Free quote |
| `about.html` | Anyone checking who is behind it | — |
| `404.html` | — | `noindex` |

**Two rules that are load-bearing:**

1. **Assembled units may not be offered for sale** until the FCC Part 15B SDoC is complete. The
   kit and the *loaner* pilot are what may be marketed today. Any copy implying an assembled unit
   is purchasable is a compliance problem, not just a wording one — see `docs/COMPLIANCE.md`.
2. **`pilot.html` and `docs/PILOT_OFFER.md` carry the same offer** and a customer may read both.
   Change them together.

Extensionless URLs (`/pilot`, `/freezer-alarm`) are used by every canonical, internal link and
sitemap entry. **Rely on the Cloudflare Pages default for this — do not add a `_redirects` file
mapping them to `.html`.** Pages already serves `foo.html` at `/foo`, *and* it 301s `/foo.html`
back to `/foo` to keep one canonical URL. A rule like `/foo /foo.html 200` therefore points at a
path Pages immediately redirects away from, and the two bounce off each other until the browser
gives up with `ERR_TOO_MANY_REDIRECTS`. A `_redirects` file written to "make the default explicit"
took all eight subpages down for about a day (`8b40876` added it, `/replacement-parts` was the
page that surfaced it). The homepage stayed up throughout, because `/` had no rule — which is what
makes this look like a zone/SSL problem when it is not.

## Deploy model

The goal is **Git auto-deploy**: connect the Cloudflare Pages project to this repo
and every push to `main` rebuilds and publishes `datumlaboratories.com`
automatically — no manual upload.

**Cloudflare Pages build settings (this is a Python-app repo, so these matter):**

| Setting | Value |
|---|---|
| Production branch | `main` |
| Build command | *(empty)* |
| Build output directory | **`site`** |
| Root directory | *(repo root — leave default)* |

The **build output directory must be `site`** so Cloudflare serves
`site/index.html` at the root and ignores the rest of the repo. Cloudflare Pages
**Functions** are discovered from the repo-root [`functions/`](../functions)
directory (see the waitlist handler below) — that is why the function lives at the
repo root, not inside `site/`.

> ⚠️ **Order of operations** (the live domain has real traffic — don't blank it):
> 1. Make sure `site/` and `functions/` are on **`main`** first (merge the branch).
> 2. Connect the Pages project to Git (or create a new Git-connected project) with
>    the settings above.
> 3. Verify on the `*.pages.dev` **preview** URL — including that the waitlist form
>    and `/api/waitlist` work — before moving the custom domain.
> 4. Point `datumlaboratories.com` (+ the other domains) at the Git deployment.
>
> A Cloudflare project is created as *Direct Upload* **or** *Git* and usually can't
> be converted — if the connect option isn't offered on the existing project,
> create a new Git-connected one and move the domain over in step 4.

**Until Git is connected**, this stays *manual*: edit here, commit, and upload
`site/index.html` to Cloudflare by hand. Once Git is connected, a push is enough.

## Waitlist form (`/api/waitlist`)

The `#reserve` form POSTs to [`functions/api/waitlist.js`](../functions/api/waitlist.js),
a Pages Function that stores signups in a Cloudflare **KV** namespace. One-time
setup in the Cloudflare dashboard:

1. **Workers & Pages → KV → Create namespace** (e.g. `setpoint-waitlist`).
2. **Pages project → Settings → Functions → KV namespace bindings** → add
   `WAITLIST` → the namespace above.
3. *(optional, to export)* **Settings → Environment variables** → secret
   `WAITLIST_TOKEN = <long random string>`. Then `GET /api/waitlist?token=…`
   returns the signups as JSON.
4. Redeploy. **Test:** submit the form on the preview URL, then confirm a
   `signup:` key appears in the KV namespace. If the binding is missing the form
   still says "you're on the list" but nothing is stored — so verify the KV entry.

`/api/contact` ([`functions/api/contact.js`](../functions/api/contact.js)) reuses the
same binding and token under a `contact:` prefix, so there is nothing extra to set up.

### Two things about these endpoints that are easy to get wrong

**Records go in KV *metadata*, not just the value.** A Worker invocation is capped
at **50 subrequests** on the free plan, and every `KV.get()` is one. The original
export walked the key list and issued a `get()` per key, so it worked in testing
and started failing at roughly 50 records — the exact point where the list becomes
worth exporting. `list()` returns metadata inline for free, so the export now costs
no `get()` at all for records written since. Anything too big for KV's **1 KiB**
metadata cap (a long contact message) still falls back to a `get()`, spent against
an explicit budget; when that budget runs out the response carries
`truncated: true` and a `cursor` to pass back as `?cursor=…`. See
[`_shared.js`](../functions/api/_shared.js).

**Rate limiting is not in the code, and needs to be in the dashboard.** The
endpoints reject foreign origins and carry a honeypot field, which stops
drive-by bots — but an `Origin` header is trivially forged, so that is a filter,
not a control. The real protection is a **WAF rate-limiting rule**: Security →
WAF → Rate limiting rules → match `http.request.uri.path in {"/api/waitlist"
"/api/contact" "/api/quote"}`, something like 5 requests per minute per IP,
action Block. Worth doing, because free-tier KV allows **1,000 writes/day**: once
that is gone, real submissions start returning `store_failed` and the only
symptom is that the list quietly stops growing.

## Replacement-parts quote form (`/api/quote`)

[`replacement-parts.html`](replacement-parts.html) is the cold-outreach landing page for
repair shops. Its form uploads photos to
[`functions/api/quote.js`](../functions/api/quote.js) as `multipart/form-data`.

**Minimum viable setup is two environment variables** — KV is already bound from the
waitlist, and photos ride along as email attachments, so **R2 is optional**:

| Binding / var | Type | Needed? | Purpose |
|---|---|---|---|
| `WAITLIST` | KV | already bound | Stores the request under a `quote:` key prefix |
| `RESEND_API_KEY` | secret | **strongly recommended** | Emails you each request *with the photos attached* |
| `QUOTE_NOTIFY_TO` | var | **strongly recommended** | Address that notification goes to |
| `QUOTE_FROM` | var | optional | From address; defaults to `Datum Labs <thomas.allen@datumlaboratories.com>` |
| `QUOTE_PHOTOS` | R2 | optional | Archives full-resolution photos beyond the email |
| `WAITLIST_TOKEN` | secret | optional | Gates the `GET` export, same as the other two forms |

1. **Sign up at resend.com**, verify `datumlaboratories.com` (add the DNS records in
   Cloudflare — this coexists with Email Routing, it doesn't replace it), and create an API key.
2. **Pages project → Settings → Environment variables** → add `RESEND_API_KEY` as a
   **secret** and `QUOTE_NOTIFY_TO` as a plain variable.
3. *(optional)* **R2 → Create bucket** (e.g. `datum-quote-photos`) → **Settings → Functions →
   R2 bucket bindings** → bind it as `QUOTE_PHOTOS`. Keep the bucket **private**; photos are
   only readable through the token-gated endpoint below.
4. Redeploy, then **submit a real test from your phone** — the point is to confirm the mobile
   camera path works, not just the desktop one.

**Reading requests:**

```
GET /api/quote?token=…                          # every request, newest first
GET /api/quote?token=…&photo=quotes/…/photo-1.jpg   # one archived photo (needs R2)
```

**Without a mail provider** the form still stores to KV and returns success, but you'd have to
poll the export to find leads — which defeats a page built for cold outreach. Set up Resend
before you send the first email. If *nothing* is configured the endpoint returns a 500 and the
page shows an error rather than a fake success screen, so a lead is never silently dropped.

**Photo handling:** the page resizes images to 1600 px through a canvas before upload, which
also strips EXIF (including GPS). The Function independently sniffs magic bytes — ignoring the
client's declared type — caps files at 6 × 8 MB (20 MB total), and strips EXIF/XMP again
server-side for JPEG, PNG and WebP. HEIC/AVIF that arrive un-transcoded pass through with
metadata intact (stripping them needs a full ISO-BMFF parser); each stored record carries an
`exif_stripped` flag per photo so you can see which is which.

**Reloadable CamScan job:** when a quote comes through the embedded CamScan tool, the handoff
includes a reloadable bundle (raw image + calibration + editable trace per view). The page
forwards it as a `camscan_job` form field (JSON, ≤15 MB); the Function attaches it to the
notification email as **`job.camscan.json`** and archives it to R2 (when bound) alongside the
photos. Download that file and use CamScan's **⤓ Load job** to reopen the shop's measured trace —
scale and annotations intact — refine it, and export a DXF. It's an opaque pass-through here; the
schema is owned by CamScan (see its `INTEGRATION.md §3`).

### Optional measuring tool (CamScan)

The page has a **"Measure it yourself (optional)"** section (`#measure`) that points shops at
[CamScan](https://github.com/tallen5431/CamScan) — a browser measuring tool — so they can send
exact dimensions with their photos. CamScan is a **Python/Dash + OpenCV app**, so it can't run on
Cloudflare Pages itself.

**It's live at [`measure.datumlaboratories.com`](https://measure.datumlaboratories.com).** It runs
self-hosted (on a dedicated box managed by [HTTP_Server](https://github.com/tallen5431/HTTP_Server)
on port `8059`) and is published to the public internet through a **Cloudflare Tunnel** —
`cloudflared` maps the subdomain to `http://localhost:8059`, so there's no open router port and the
home IP stays hidden. The tunnel runs as a `systemd` service (`cloudflared.service`), so it survives
reboots; CamScan itself must be running (flip its **Autostart** toggle in the HTTP_Server manager)
for the tunnel to have something to serve.

> Because it's self-hosted, the Measure button depends on that box being on. If the machine is off or
> CamScan is stopped, the button opens a dead tab. It's an *optional* step (shops can just lay a coin
> or ruler in the photo), so this degrades softly — but keep it in mind.

The link is controlled by one constant near the top of the `<script>` block in `replacement-parts.html`:

```js
var MEASURE_URL = "https://measure.datumlaboratories.com";   // hosted CamScan
```

Set it to `""` to fall back to the safe **"coming soon"** state (no dead link) if the tool ever goes offline.

> **Filling the "Capability demo" section:** it ships with one honest demo case (framed as a
> demonstration build, *not* a customer job) with empty photo slots. Drop three images into
> `site/parts/` — broken / measured / printed — and swap each placeholder `.shot` div for an
> `<img>`, then write the caption. Copy the `.case` block to add more demos or real jobs as they
> come in. It's safe to show as-is, but real photos make it land.

## Keep in sync by hand

Some facts must match the rest of the repo and the live listing when they change:

- **DIY kit price** — currently **$39** (matches the Tindie listing / `docs/BOM.md`).
- **Battery life** — currently "weeks" pending bench testing; raise only once the
  real number is confirmed (see `docs/TINDIE_LISTING.md` honest-specs framing).
- **Tindie "Buy" link** — the DIY card links to the live Tindie product URL.
- **Contact email** — `thomas.allen@datumlaboratories.com` (Zoho Mail mailbox). This is the address
  shown in every `mailto:` link on the site and the default `QUOTE_FROM`/`QUOTE_NOTIFY_TO` target, so
  the whole site reaches one inbox with no aliases required. (Cloudflare Email Routing is retired now
  that the domain's MX points at Zoho — the two can't both own MX.)
- **Replacement-part pricing (tiered)** — **print-from-your-file** (material + $15),
  **simple replacement** ($29–60), **reverse-engineered** ($75–250, most ~$120), **design from
  scratch** (quoted). Plus **$25 minimum**, **quote in 24 h**, **ships in 3–5 business days**,
  **first simple part free for repair shops**. The numbers appear in the hero trust bar ("from $29")
  and the pricing cards on `replacement-parts.html` **and across all the go-to-market copy** —
  `docs/ETSY_EBAY_LISTINGS.md`, `docs/OUTREACH_EMAIL.md`, and `docs/COMMUNITY_POSTS.md`. Change them
  together or they'll contradict each other. Marketplace (Etsy/eBay) prices should run ~10–15 %
  above these to cover platform fees.
- **General print services** — the "Print from your file" tier and the "What I make" note invite
  general 3D-print jobs (send an STL), not only replacements.
- **Go-to-market collateral** lives in `docs/`: `ETSY_EBAY_LISTINGS.md` (made-to-order marketplace
  copy), `OUTREACH_EMAIL.md` (cold email to repair shops), `COMMUNITY_POSTS.md` (Reddit / Facebook).
  All point back to `datumlaboratories.com/replacement-parts`.

## Related (auto-deployed elsewhere — not this site)

`web/**`, `flash/**`, and `docs/images/assembly/**` publish to
**setpoint.datumlaboratories.com** via `.github/workflows/deploy-flasher.yml`
(GitHub Pages). That is a *separate* site from this one.
