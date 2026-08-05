// Cloudflare Pages Function — waitlist capture for datumlaboratories.com
// Route: /api/waitlist  (POST to sign up, GET to export)
//
// This replaces the old front-end-only form that showed "You're on the list"
// but stored nothing. Signups are written to a Cloudflare KV namespace.
//
// ── One-time setup in the Cloudflare dashboard ──────────────────────────────
//  1. Workers & Pages → KV → Create a namespace, e.g. "setpoint-waitlist".
//  2. Your Pages project → Settings → Functions → KV namespace bindings → add:
//        Variable name = WAITLIST      KV namespace = setpoint-waitlist
//  3. (Optional, to export the list) Settings → Environment variables → add a
//        secret  WAITLIST_TOKEN = <a long random string>.
//  4. Redeploy (push, or "Retry deployment").
//
// NOTE: this file must live at the REPO ROOT under functions/ (not inside
// site/). Cloudflare Pages discovers Functions from the project-root functions/
// directory; the static page is served from the build output dir (site/).
//
// If the WAITLIST binding is missing the endpoint still returns success so a
// visitor never sees an error, but it logs a warning and does NOT persist —
// after a test signup, confirm the KV namespace actually has a key.

import { json, clip, timingSafeEqual, isAllowedOrigin, allowedHostsFor,
         exportRecords, fitsMetadata } from "./_shared.js";

const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

// POST /api/waitlist  { email }  → stores one signup, idempotent per email.
export async function onRequestPost({ request, env }) {
  // Cheap drive-by filter. Free-tier KV allows 1,000 writes/day, so an
  // unauthenticated write endpoint that anything can POST to in a loop is a
  // silent outage waiting to happen: the quota goes, then real signups start
  // returning store_failed and the only symptom is that the list stops growing.
  if (!isAllowedOrigin(request, allowedHostsFor(request, env))) {
    return json({ ok: false, error: "forbidden_origin" }, 403);
  }

  let email = "";
  let trap = "";
  try {
    const ct = request.headers.get("content-type") || "";
    if (ct.indexOf("application/json") !== -1) {
      const data = await request.json();
      email = clip((data && data.email) || "", 254);
      trap = clip((data && data.company) || "", 80);
    } else {
      const form = await request.formData();
      email = clip(form.get("email") || "", 254);
      trap = clip(form.get("company") || "", 80);
    }
  } catch (e) {
    return json({ ok: false, error: "bad_request" }, 400);
  }

  // Honeypot: the form ships a `company` field hidden from humans via CSS. A
  // real visitor never fills it; a form-filling bot fills everything. Answer 200
  // so the bot sees success and does not retry, but store nothing.
  if (trap) return json({ ok: true, stored: true });

  // Never trust the client — validate server-side too.
  if (!EMAIL_RE.test(email) || email.length > 254) {
    return json({ ok: false, error: "invalid_email" }, 422);
  }

  if (!env.WAITLIST) {
    // Binding not configured yet: don't 500 on the visitor, but make it loud
    // in the logs so the owner notices before launch.
    console.warn("waitlist: KV binding 'WAITLIST' is not bound; NOT stored:", email);
    return json({ ok: true, stored: false });
  }

  try {
    const key = "signup:" + email.toLowerCase();
    const existing = await env.WAITLIST.get(key);
    if (existing) {
      return json({ ok: true, stored: true, duplicate: true });
    }
    const record = {
      email: email,
      ts: new Date().toISOString(),
      ref: clip(request.headers.get("referer") || "", 300),
      ua: clip(request.headers.get("user-agent") || "", 300),
      country: (request.cf && request.cf.country) || "",
    };
    // Write the record to metadata as well as the value. list() returns
    // metadata inline, so the export below reads the whole list without a
    // per-key get() — see exportRecords() for why that matters. ref/ua are
    // clipped above to keep the record inside KV's 1 KiB metadata limit.
    await env.WAITLIST.put(key, JSON.stringify(record), { metadata: fitsMetadata(record) });
    return json({ ok: true, stored: true });
  } catch (e) {
    return json({ ok: false, error: "store_failed" }, 500);
  }
}

// GET /api/waitlist?token=…[&cursor=…]  → JSON export of signups (newest first).
// Gated by the WAITLIST_TOKEN secret; returns 405 until that secret is set so
// the endpoint isn't publicly listable by accident.
//
// If `truncated` is true, pass the returned `cursor` back as ?cursor= to get the
// next page. That only happens for records written before metadata was stored.
export async function onRequestGet({ request, env }) {
  if (!env.WAITLIST_TOKEN) {
    return new Response("Method Not Allowed", { status: 405 });
  }
  const url = new URL(request.url);
  const token = url.searchParams.get("token") || "";
  if (!timingSafeEqual(token, env.WAITLIST_TOKEN)) {
    return new Response("Forbidden", { status: 403 });
  }
  if (!env.WAITLIST) {
    return json({ ok: true, count: 0, signups: [] });
  }
  const { records, truncated, cursor } = await exportRecords(
    env, "signup:", { cursor: url.searchParams.get("cursor") || undefined });
  return json({ ok: true, count: records.length, truncated, cursor, signups: records });
}
