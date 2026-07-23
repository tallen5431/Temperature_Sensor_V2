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

const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

function json(body, status) {
  return new Response(JSON.stringify(body), {
    status: status || 200,
    headers: { "content-type": "application/json; charset=utf-8" },
  });
}

// POST /api/waitlist  { email }  → stores one signup, idempotent per email.
export async function onRequestPost({ request, env }) {
  let email = "";
  try {
    const ct = request.headers.get("content-type") || "";
    if (ct.indexOf("application/json") !== -1) {
      const data = await request.json();
      email = String((data && data.email) || "").trim();
    } else {
      const form = await request.formData();
      email = String(form.get("email") || "").trim();
    }
  } catch (e) {
    return json({ ok: false, error: "bad_request" }, 400);
  }

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
      ref: request.headers.get("referer") || "",
      ua: request.headers.get("user-agent") || "",
      country: (request.cf && request.cf.country) || "",
    };
    await env.WAITLIST.put(key, JSON.stringify(record));
    return json({ ok: true, stored: true });
  } catch (e) {
    return json({ ok: false, error: "store_failed" }, 500);
  }
}

// GET /api/waitlist?token=…  → JSON export of every signup (newest first).
// Gated by the WAITLIST_TOKEN secret; returns 405 until that secret is set so
// the endpoint isn't publicly listable by accident.
export async function onRequestGet({ request, env }) {
  if (!env.WAITLIST_TOKEN) {
    return new Response("Method Not Allowed", { status: 405 });
  }
  const token = new URL(request.url).searchParams.get("token") || "";
  if (token !== env.WAITLIST_TOKEN) {
    return new Response("Forbidden", { status: 403 });
  }
  if (!env.WAITLIST) {
    return json({ ok: true, count: 0, signups: [] });
  }
  const signups = [];
  let cursor;
  do {
    const page = await env.WAITLIST.list({ prefix: "signup:", cursor: cursor });
    for (const k of page.keys) {
      const v = await env.WAITLIST.get(k.name);
      if (v) {
        try { signups.push(JSON.parse(v)); } catch (e) { /* skip bad row */ }
      }
    }
    cursor = page.list_complete ? undefined : page.cursor;
  } while (cursor);
  signups.sort(function (a, b) { return a.ts < b.ts ? 1 : -1; });
  return json({ ok: true, count: signups.length, signups: signups });
}
