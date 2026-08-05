// Cloudflare Pages Function — contact / "work with us" inquiries
// Route: /api/contact  (POST to send, GET to export)
//
// Reuses the SAME KV binding and export token as the waitlist, so there is no
// extra Cloudflare setup: inquiries are stored under a "contact:" key prefix in
// the WAITLIST namespace, keeping them separate from "signup:" waitlist entries.
//   - Requires the KV binding `WAITLIST` (already bound for the waitlist form).
//   - Export (GET ?token=…) reuses the `WAITLIST_TOKEN` secret.
//
// This file must live at the repo root under functions/ (where Cloudflare Pages
// discovers Functions); the static pages are served from the build output (site/).

import { json, clip, timingSafeEqual, isAllowedOrigin, allowedHostsFor,
         exportRecords, fitsMetadata } from "./_shared.js";

const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
const THROTTLE_SEC = 60;

// POST /api/contact  { name, email, service, message }
export async function onRequestPost({ request, env }) {
  if (!isAllowedOrigin(request, allowedHostsFor(request, env))) {
    return json({ ok: false, error: "forbidden_origin" }, 403);
  }

  let data = {};
  try {
    const ct = request.headers.get("content-type") || "";
    if (ct.indexOf("application/json") !== -1) {
      data = await request.json();
    } else {
      const form = await request.formData();
      data = {
        name: form.get("name"),
        email: form.get("email"),
        service: form.get("service"),
        message: form.get("message"),
        company: form.get("company"),
      };
    }
  } catch (e) {
    return json({ ok: false, error: "bad_request" }, 400);
  }

  const email = clip(data.email, 254);
  const message = clip(data.message, 5000);
  const name = clip(data.name, 200);
  const service = clip(data.service, 80);
  const trap = clip(data.company, 80);

  // Honeypot — see waitlist.js. Report success so the bot moves on.
  if (trap) return json({ ok: true, stored: true });

  if (!EMAIL_RE.test(email)) return json({ ok: false, error: "invalid_email" }, 422);
  if (message.length < 2) return json({ ok: false, error: "empty_message" }, 422);

  if (!env.WAITLIST) {
    console.warn("contact: KV binding 'WAITLIST' is not bound; NOT stored:", email);
    return json({ ok: true, stored: false });
  }

  try {
    // Per-sender throttle. Unlike the waitlist — which keys on the email and so
    // is naturally idempotent — every inquiry gets a unique key, meaning one
    // sender could write unboundedly and burn the 1,000/day free KV write quota.
    // Checking a short-lived marker first makes a flood cost reads (100k/day)
    // instead of writes, so the endpoint degrades to "slow down" rather than
    // taking real inquiries down with it.
    const throttleKey = "rl:contact:" + email.toLowerCase();
    if (await env.WAITLIST.get(throttleKey)) {
      return json({ ok: false, error: "too_many_requests" }, 429);
    }

    const id = (crypto && crypto.randomUUID) ? crypto.randomUUID() : String(Math.random()).slice(2);
    const ts = new Date().toISOString();
    const record = {
      name: name,
      email: email,
      service: service,
      message: message,
      ts: ts,
      ref: clip(request.headers.get("referer") || "", 300),
      country: (request.cf && request.cf.country) || "",
    };
    // Time-ordered key so exports read newest-first when reversed; unique via UUID.
    // Metadata carries the record when it fits KV's 1 KiB cap, so the export can
    // read it back from list() without a per-key get(); a long message simply
    // falls back to a budgeted get. See exportRecords().
    await env.WAITLIST.put(`contact:${ts}:${id}`, JSON.stringify(record),
                           { metadata: fitsMetadata(record) });
    await env.WAITLIST.put(throttleKey, "1", { expirationTtl: THROTTLE_SEC });
    return json({ ok: true, stored: true });
  } catch (e) {
    return json({ ok: false, error: "store_failed" }, 500);
  }
}

// GET /api/contact?token=…[&cursor=…]  → JSON export of inquiries (newest first).
// See waitlist.js for the pagination contract.
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
    return json({ ok: true, count: 0, inquiries: [] });
  }
  const { records, truncated, cursor } = await exportRecords(
    env, "contact:", { cursor: url.searchParams.get("cursor") || undefined });
  return json({ ok: true, count: records.length, truncated, cursor, inquiries: records });
}
