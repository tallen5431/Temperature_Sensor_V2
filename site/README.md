# site/ — datumlaboratories.com (marketing landing page)

Source of record for the **public marketing/landing page at `datumlaboratories.com`**
(hero, specs, "three ways to run", and the reserve/waitlist section).

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

### Optional measuring tool (CamScan)

The page has a **"Measure it yourself (optional)"** section (`#measure`) that points shops at
[CamScan](https://github.com/tallen5431/CamScan) — a browser measuring tool — so they can send
exact dimensions with their photos. CamScan is a **Python/Dash + OpenCV app**, so it can't run on
Cloudflare Pages itself; it has to be hosted somewhere with a Python runtime (Render, Fly.io,
HuggingFace Spaces, a small VPS, etc.), ideally behind a subdomain like `measure.datumlaboratories.com`.

Until it's hosted, the button shows a **"coming soon"** state — no dead link ships. To switch it on,
set one constant near the top of the `<script>` block in `replacement-parts.html`:

```js
var MEASURE_URL = "https://measure.datumlaboratories.com";   // your hosted CamScan URL
```

The moment it's non-empty, the button links out to the tool; leave it `""` to keep the coming-soon state.

> ⚠ **Before sending this page in an email:** replace the four placeholder case slots in the
> proof gallery with real jobs and delete the amber build-note box. The page ships with them
> visibly unfinished on purpose so it can't go out looking like fabricated work. Two real cases
> beat four invented ones.

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
- **Replacement-part price + turnaround** — currently **$75–250 (most ~$120)**, **quote in 24 h**,
  **ships in 3–5 business days**, **first simple part free**. These appear in three places on
  `replacement-parts.html` (hero trust bar, process step 3, pricing cards) **and in the cold
  outreach email** — change them together or the email will contradict the page.

## Related (auto-deployed elsewhere — not this site)

`web/**`, `flash/**`, and `docs/images/assembly/**` publish to
**setpoint.datumlaboratories.com** via `.github/workflows/deploy-flasher.yml`
(GitHub Pages). That is a *separate* site from this one.
