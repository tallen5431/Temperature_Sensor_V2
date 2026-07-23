# site/ — datumlaboratories.com (marketing landing page)

Source of record for the **public marketing/landing page at `datumlaboratories.com`**
(the hero, specs, "three ways to run", and the reserve/waitlist section).

## ⚠️ This folder is MANUAL DEPLOY — CI does not publish it

Editing a file here updates the *source of record only*. **Nothing in this repo
deploys `site/`.** For a change to go live on `datumlaboratories.com` you must
**manually upload the file to Cloudflare** yourself.

Contrast with the rest of the web presence, which *is* auto-published:

| What | Files in repo | Deploys to | How |
|---|---|---|---|
| **Marketing page** | `site/index.html` | **datumlaboratories.com** | **MANUAL** — upload to Cloudflare |
| Setup / "Start Here" | `web/*.html` | setpoint.datumlaboratories.com | Auto — `deploy-flasher.yml` (GitHub Pages) on push |
| Browser flasher | `flash/**` | setpoint.datumlaboratories.com/flash/ | Auto — same workflow |
| Assembly photos | `docs/images/assembly/**` | setpoint.datumlaboratories.com/img/assembly/ | Auto — same workflow |

So: a push that touches `web/`, `flash/`, or `docs/images/assembly/` goes live on
the **setup** site by itself. A push that touches `site/` does **not** — you have
to re-upload it to Cloudflare.

## To deploy a change to datumlaboratories.com

1. Edit `site/index.html` here and commit/push (keeps history + a backup).
2. Cloudflare dashboard → the `datumlaboratories.com` project → **upload
   `site/index.html`** (replace the current file).
3. Confirm the live page.

## Not represented in this repo (lives only in Cloudflare)

- **The waitlist form handler.** The `#reserve` form in `index.html` is markup
  only; the actual capture (form endpoint / Cloudflare Pages Function / email
  provider) is wired on the Cloudflare side and is **not** in this repo. After a
  manual re-upload, re-confirm the form still captures — replacing the HTML can
  drop the handler wiring if it lived in the same file.

## Keep in sync by hand

Because CI can't see this file, some facts must be updated here **and** on the
live page **and** kept consistent with the rest of the repo when they change:

- **DIY kit price** — currently **$39** (matches the Tindie listing / `docs/BOM.md`).
- **Battery life** — currently "weeks" pending bench testing; raise only once the
  real number is confirmed (see `docs/TINDIE_LISTING.md` for the honest-specs framing).
- **Tindie "Buy" link** — the DIY card links to the live Tindie product URL.
- **Support email** — `support@datumlaboratories.com` (Cloudflare Email Routing → inbox).
