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

const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

function json(body, status) {
  return new Response(JSON.stringify(body), {
    status: status || 200,
    headers: { "content-type": "application/json; charset=utf-8" },
  });
}

function clip(v, max) {
  return String(v == null ? "" : v).trim().slice(0, max);
}

// POST /api/contact  { name, email, service, message }
export async function onRequestPost({ request, env }) {
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
      };
    }
  } catch (e) {
    return json({ ok: false, error: "bad_request" }, 400);
  }

  const email = clip(data.email, 254);
  const message = clip(data.message, 5000);
  const name = clip(data.name, 200);
  const service = clip(data.service, 80);

  if (!EMAIL_RE.test(email)) return json({ ok: false, error: "invalid_email" }, 422);
  if (message.length < 2) return json({ ok: false, error: "empty_message" }, 422);

  if (!env.WAITLIST) {
    console.warn("contact: KV binding 'WAITLIST' is not bound; NOT stored:", email);
    return json({ ok: true, stored: false });
  }

  try {
    const id = (crypto && crypto.randomUUID) ? crypto.randomUUID() : String(Math.random()).slice(2);
    const ts = new Date().toISOString();
    const record = {
      name: name,
      email: email,
      service: service,
      message: message,
      ts: ts,
      ref: request.headers.get("referer") || "",
      country: (request.cf && request.cf.country) || "",
    };
    // Time-ordered key so exports read newest-first when reversed; unique via UUID.
    await env.WAITLIST.put(`contact:${ts}:${id}`, JSON.stringify(record));
    return json({ ok: true, stored: true });
  } catch (e) {
    return json({ ok: false, error: "store_failed" }, 500);
  }
}

// GET /api/contact?token=…  → JSON export of every inquiry (newest first).
export async function onRequestGet({ request, env }) {
  if (!env.WAITLIST_TOKEN) {
    return new Response("Method Not Allowed", { status: 405 });
  }
  const token = new URL(request.url).searchParams.get("token") || "";
  if (token !== env.WAITLIST_TOKEN) {
    return new Response("Forbidden", { status: 403 });
  }
  if (!env.WAITLIST) {
    return json({ ok: true, count: 0, inquiries: [] });
  }
  const inquiries = [];
  let cursor;
  do {
    const page = await env.WAITLIST.list({ prefix: "contact:", cursor: cursor });
    for (const k of page.keys) {
      const v = await env.WAITLIST.get(k.name);
      if (v) {
        try { inquiries.push(JSON.parse(v)); } catch (e) { /* skip bad row */ }
      }
    }
    cursor = page.list_complete ? undefined : page.cursor;
  } while (cursor);
  inquiries.sort(function (a, b) { return a.ts < b.ts ? 1 : -1; });
  return json({ ok: true, count: inquiries.length, inquiries: inquiries });
}
