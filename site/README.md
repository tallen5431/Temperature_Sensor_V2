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

## Keep in sync by hand

Some facts must match the rest of the repo and the live listing when they change:

- **DIY kit price** — currently **$39** (matches the Tindie listing / `docs/BOM.md`).
- **Battery life** — currently "weeks" pending bench testing; raise only once the
  real number is confirmed (see `docs/TINDIE_LISTING.md` honest-specs framing).
- **Tindie "Buy" link** — the DIY card links to the live Tindie product URL.
- **Support email** — `support@datumlaboratories.com` (Cloudflare Email Routing → inbox).

## Related (auto-deployed elsewhere — not this site)

`web/**`, `flash/**`, and `docs/images/assembly/**` publish to
**setpoint.datumlaboratories.com** via `.github/workflows/deploy-flasher.yml`
(GitHub Pages). That is a *separate* site from this one.
