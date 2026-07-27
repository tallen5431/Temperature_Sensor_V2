// Cloudflare Pages Function — replacement-part quote requests (with photos)
// Route: /api/quote   POST to submit · GET to export (token-gated)
//
// Backs the form on site/replacement-parts.html. Designed so the page WORKS with
// the bindings you already have, and gets better as you add optional ones:
//
//   WAITLIST        KV     (already bound) — the request record, "quote:" prefix
//   RESEND_API_KEY  secret (recommended)   — emails you the request + photos
//   QUOTE_NOTIFY_TO var    (recommended)   — where that email goes
//   QUOTE_FROM      var    (optional)      — from address, must be a Resend-verified domain
//   QUOTE_PHOTOS    R2     (optional)      — archives full photos beyond the email
//
// With none of them bound the endpoint still answers 200 so the form never looks
// broken to a customer — but it logs loudly and reports what it did NOT store.
// Setup steps are in site/README.md.
//
// Photos never become public: R2 objects are private and only readable through
// the token-gated GET below.

const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

const MAX_FILES = 6;
const MAX_FILE_BYTES = 8 * 1024 * 1024;    // per photo
const MAX_TOTAL_BYTES = 20 * 1024 * 1024;  // all photos combined
const RATE_LIMIT = 5;                      // submissions per IP per minute

function json(body, status) {
  return new Response(JSON.stringify(body), {
    status: status || 200,
    headers: { "content-type": "application/json; charset=utf-8" },
  });
}

function clip(v, max) {
  return String(v == null ? "" : v).trim().slice(0, max);
}

function escapeHtml(s) {
  return String(s).replace(/[&<>"']/g, function (c) {
    return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c];
  });
}

/* ---------------------------------------------------------------- bytes ---- */

function concat(parts) {
  let n = 0;
  for (const p of parts) n += p.length;
  const out = new Uint8Array(n);
  let o = 0;
  for (const p of parts) { out.set(p, o); o += p.length; }
  return out;
}

function toBase64(bytes) {
  let bin = "";
  const CHUNK = 0x8000;
  for (let i = 0; i < bytes.length; i += CHUNK) {
    bin += String.fromCharCode.apply(null, bytes.subarray(i, i + CHUNK));
  }
  return btoa(bin);
}

function ascii(bytes, off, len) {
  let s = "";
  for (let i = off; i < off + len && i < bytes.length; i++) s += String.fromCharCode(bytes[i]);
  return s;
}

/* ------------------------------------------------------- type detection ---- */

// Trust the bytes, never the client-supplied Content-Type or file extension.
function sniff(bytes) {
  if (bytes.length < 12) return null;
  if (bytes[0] === 0xFF && bytes[1] === 0xD8 && bytes[2] === 0xFF) {
    return { mime: "image/jpeg", ext: "jpg" };
  }
  if (bytes[0] === 0x89 && bytes[1] === 0x50 && bytes[2] === 0x4E && bytes[3] === 0x47 &&
      bytes[4] === 0x0D && bytes[5] === 0x0A && bytes[6] === 0x1A && bytes[7] === 0x0A) {
    return { mime: "image/png", ext: "png" };
  }
  if (ascii(bytes, 0, 4) === "RIFF" && ascii(bytes, 8, 4) === "WEBP") {
    return { mime: "image/webp", ext: "webp" };
  }
  if (ascii(bytes, 4, 4) === "ftyp") {
    const brand = ascii(bytes, 8, 4);
    if (["heic", "heix", "hevc", "hevx", "heim", "heis", "mif1", "msf1"].indexOf(brand) !== -1) {
      return { mime: "image/heic", ext: "heic" };
    }
    if (brand === "avif" || brand === "avis") return { mime: "image/avif", ext: "avif" };
  }
  return null;
}

/* ----------------------------------------------------------- EXIF strip ---- */
// The page already re-encodes photos through a canvas, which drops EXIF client
// side. These run anyway as defence in depth: a submission with JS disabled, or
// a direct curl POST, reaches the server with metadata (including GPS) intact.

// JPEG: copy segments, dropping APP1–APPn (EXIF/XMP/IPTC) and COM. Everything
// from the start-of-scan marker onward is entropy-coded data and is copied raw.
function stripJpeg(bytes) {
  if (bytes.length < 4 || bytes[0] !== 0xFF || bytes[1] !== 0xD8) return bytes;
  const out = [bytes.subarray(0, 2)];
  let i = 2;
  while (i < bytes.length) {
    if (bytes[i] !== 0xFF) break;                       // desync — stop rewriting
    let m = i + 1;
    while (m < bytes.length && bytes[m] === 0xFF) m++;  // skip fill bytes
    if (m >= bytes.length) break;
    const marker = bytes[m];
    if (marker === 0xDA) { out.push(bytes.subarray(i)); return concat(out); }  // SOS → rest verbatim
    if (marker === 0x01 || (marker >= 0xD0 && marker <= 0xD9)) {               // standalone
      out.push(bytes.subarray(i, m + 1));
      i = m + 1;
      continue;
    }
    if (m + 2 >= bytes.length) break;
    const len = (bytes[m + 1] << 8) | bytes[m + 2];
    if (len < 2 || m + 1 + len > bytes.length) break;
    const end = m + 1 + len;
    const drop = (marker >= 0xE1 && marker <= 0xEF) || marker === 0xFE;
    if (!drop) out.push(bytes.subarray(i, end));
    i = end;
  }
  if (i < bytes.length) out.push(bytes.subarray(i));    // tail after a desync
  return concat(out);
}

// PNG: drop eXIf and the text chunks, keep the rest byte-for-byte. Chunk CRCs
// cover only their own chunk, so removing whole chunks needs no recompute.
function stripPng(bytes) {
  if (bytes.length < 8) return bytes;
  const out = [bytes.subarray(0, 8)];
  const drop = { "eXIf": 1, "tEXt": 1, "zTXt": 1, "iTXt": 1 };
  let i = 8;
  while (i + 8 <= bytes.length) {
    const len = (bytes[i] << 24 | bytes[i + 1] << 16 | bytes[i + 2] << 8 | bytes[i + 3]) >>> 0;
    const type = ascii(bytes, i + 4, 4);
    const end = i + 12 + len;
    if (end > bytes.length) break;
    if (!drop[type]) out.push(bytes.subarray(i, end));
    i = end;
    if (type === "IEND") return concat(out);
  }
  if (i < bytes.length) out.push(bytes.subarray(i));
  return concat(out);
}

// WebP (RIFF): drop the EXIF and XMP chunks, then rewrite the RIFF payload size.
function stripWebp(bytes) {
  if (bytes.length < 12) return bytes;
  const kept = [];
  let i = 12;
  while (i + 8 <= bytes.length) {
    const fourcc = ascii(bytes, i, 4);
    const size = (bytes[i + 4] | bytes[i + 5] << 8 | bytes[i + 6] << 16 | bytes[i + 7] << 24) >>> 0;
    const padded = size + (size % 2);
    const end = i + 8 + padded;
    if (end > bytes.length) break;
    if (fourcc !== "EXIF" && fourcc !== "XMP ") kept.push(bytes.subarray(i, end));
    i = end;
  }
  if (!kept.length) return bytes;
  let payload = 4;                                   // the "WEBP" fourcc
  for (const k of kept) payload += k.length;
  const header = new Uint8Array(12);
  header.set(bytes.subarray(0, 12));
  header[4] = payload & 0xFF;
  header[5] = (payload >> 8) & 0xFF;
  header[6] = (payload >> 16) & 0xFF;
  header[7] = (payload >> 24) & 0xFF;
  return concat([header].concat(kept));
}

// Returns { bytes, stripped }. HEIC/AVIF store EXIF inside an ISO-BMFF meta box;
// removing it safely needs a real container parser, which isn't worth shipping in
// a Worker — so those pass through unmodified and the record says so. In practice
// the client canvas re-encode turns almost every HEIC into a clean JPEG first.
function stripMetadata(bytes, mime) {
  try {
    if (mime === "image/jpeg") return { bytes: stripJpeg(bytes), stripped: true };
    if (mime === "image/png") return { bytes: stripPng(bytes), stripped: true };
    if (mime === "image/webp") return { bytes: stripWebp(bytes), stripped: true };
  } catch (e) {
    return { bytes: bytes, stripped: false };        // never fail a submission over metadata
  }
  return { bytes: bytes, stripped: false };
}

/* ---------------------------------------------------------------- email ---- */

async function notify(env, record, photos) {
  if (!env.RESEND_API_KEY || !env.QUOTE_NOTIFY_TO) return false;

  const rows = [
    ["Shop", record.shop],
    ["Name", record.name],
    ["Email", record.email],
    ["Phone", record.phone || "—"],
    ["Photos", String(photos.length)],
    ["Received", record.ts],
  ].map(function (r) {
    return "<tr><td style=\"padding:4px 14px 4px 0;color:#666\">" + escapeHtml(r[0]) +
           "</td><td style=\"padding:4px 0\"><b>" + escapeHtml(r[1]) + "</b></td></tr>";
  }).join("");

  const html =
    '<div style="font-family:-apple-system,Segoe UI,Roboto,sans-serif;font-size:15px;line-height:1.6">' +
    '<h2 style="margin:0 0 14px">Part quote request — ' + escapeHtml(record.shop) + "</h2>" +
    '<table style="border-collapse:collapse;margin-bottom:16px">' + rows + "</table>" +
    '<div style="background:#f5f6f4;border-left:3px solid #0E94AB;padding:12px 16px;white-space:pre-wrap">' +
    escapeHtml(record.description || "(no description given)") + "</div>" +
    '<p style="color:#666;font-size:13px;margin-top:18px">Photos attached. Reply straight to this email — it goes to the shop.</p>' +
    "</div>";

  const body = {
    from: env.QUOTE_FROM || "Datum Labs <thomas.allen@datumlaboratories.com>",
    to: [env.QUOTE_NOTIFY_TO],
    reply_to: record.email,
    subject: "Part quote — " + record.shop + " (" + photos.length + " photo" + (photos.length === 1 ? "" : "s") + ")",
    html: html,
    attachments: photos.map(function (p) {
      return { filename: p.filename, content: toBase64(p.bytes) };
    }),
  };

  try {
    const res = await fetch("https://api.resend.com/emails", {
      method: "POST",
      headers: {
        "authorization": "Bearer " + env.RESEND_API_KEY,
        "content-type": "application/json",
      },
      body: JSON.stringify(body),
    });
    if (!res.ok) {
      console.error("quote: email send failed", res.status, await res.text());
      return false;
    }
    return true;
  } catch (e) {
    console.error("quote: email threw", e);
    return false;
  }
}

/* ----------------------------------------------------------- rate limit ---- */
// A speed bump, not a guarantee — KV is eventually consistent, so a fast burst
// from one IP can slip through. Enough to stop someone looping 20 MB uploads.
async function rateLimited(env, ip) {
  if (!env.WAITLIST || !ip) return false;
  const key = "rl:quote:" + ip;
  try {
    const n = parseInt((await env.WAITLIST.get(key)) || "0", 10);
    if (n >= RATE_LIMIT) return true;
    await env.WAITLIST.put(key, String(n + 1), { expirationTtl: 60 });
  } catch (e) { /* never block a real customer on limiter failure */ }
  return false;
}

/* ------------------------------------------------------------------ POST --- */

export async function onRequestPost({ request, env }) {
  const ip = request.headers.get("cf-connecting-ip") || "";
  if (await rateLimited(env, ip)) return json({ ok: false, error: "rate_limited" }, 429);

  let form;
  try {
    form = await request.formData();
  } catch (e) {
    return json({ ok: false, error: "bad_request" }, 400);
  }

  const name = clip(form.get("name"), 120);
  const shop = clip(form.get("shop"), 160);
  const email = clip(form.get("email"), 254);
  const phone = clip(form.get("phone"), 40);
  const description = clip(form.get("description"), 4000);

  if (!EMAIL_RE.test(email)) return json({ ok: false, error: "invalid_email" }, 422);
  if (!name || !shop) return json({ ok: false, error: "missing_fields" }, 422);

  const uploads = form.getAll("photos").filter(function (f) {
    return f && typeof f.arrayBuffer === "function" && f.size > 0;
  });
  if (!uploads.length) return json({ ok: false, error: "no_photos" }, 422);
  if (uploads.length > MAX_FILES) return json({ ok: false, error: "too_many" }, 422);

  let total = 0;
  const photos = [];
  for (let i = 0; i < uploads.length; i++) {
    const f = uploads[i];
    if (f.size > MAX_FILE_BYTES) return json({ ok: false, error: "too_large" }, 413);
    total += f.size;
    if (total > MAX_TOTAL_BYTES) return json({ ok: false, error: "too_large" }, 413);

    const raw = new Uint8Array(await f.arrayBuffer());
    const kind = sniff(raw);
    if (!kind) return json({ ok: false, error: "bad_type" }, 415);

    const cleaned = stripMetadata(raw, kind.mime);
    photos.push({
      filename: "photo-" + (i + 1) + "." + kind.ext,
      mime: kind.mime,
      bytes: cleaned.bytes,
      size: cleaned.bytes.length,
      exif_stripped: cleaned.stripped,
    });
  }

  const id = (typeof crypto !== "undefined" && crypto.randomUUID) ? crypto.randomUUID() : String(Math.random()).slice(2);
  const ts = new Date().toISOString();
  const record = {
    kind: "replacement_part",
    name: name,
    shop: shop,
    email: email,
    phone: phone,
    description: description,
    ts: ts,
    ref: request.headers.get("referer") || "",
    country: (request.cf && request.cf.country) || "",
    photos: photos.map(function (p) {
      return { filename: p.filename, mime: p.mime, size: p.size, exif_stripped: p.exif_stripped };
    }),
  };

  // Archive the full photos in R2 when it's bound; the email carries them either way.
  let archived = false;
  if (env.QUOTE_PHOTOS) {
    try {
      const prefix = "quotes/" + ts + "-" + id + "/";
      await Promise.all(photos.map(function (p) {
        return env.QUOTE_PHOTOS.put(prefix + p.filename, p.bytes, {
          httpMetadata: { contentType: p.mime },
        });
      }));
      record.photo_prefix = prefix;
      archived = true;
    } catch (e) {
      console.error("quote: R2 archive failed", e);
    }
  }

  const emailed = await notify(env, record, photos);
  record.emailed = emailed;

  let stored = false;
  if (env.WAITLIST) {
    try {
      await env.WAITLIST.put("quote:" + ts + ":" + id, JSON.stringify(record));
      stored = true;
    } catch (e) {
      console.error("quote: KV store failed", e);
    }
  }

  // A request that reached nothing at all is a real failure — say so rather than
  // showing the customer a success screen over a dropped lead.
  if (!emailed && !stored && !archived) {
    console.error("quote: NOT CAPTURED — no KV, no email, no R2:", email, shop);
    return json({ ok: false, error: "not_configured" }, 500);
  }

  return json({ ok: true, stored: stored, emailed: emailed, archived: archived });
}

/* ------------------------------------------------------------------- GET --- */
// Export requests as JSON, or fetch one archived photo:
//   GET /api/quote?token=…                       → every request, newest first
//   GET /api/quote?token=…&photo=quotes/…/x.jpg  → that image from R2
// Reuses WAITLIST_TOKEN; returns 405 until that secret exists so nothing is
// publicly listable by accident.
export async function onRequestGet({ request, env }) {
  if (!env.WAITLIST_TOKEN) return new Response("Method Not Allowed", { status: 405 });

  const url = new URL(request.url);
  if (url.searchParams.get("token") !== env.WAITLIST_TOKEN) {
    return new Response("Forbidden", { status: 403 });
  }

  const photo = url.searchParams.get("photo");
  if (photo) {
    if (!env.QUOTE_PHOTOS) return new Response("Not Found", { status: 404 });
    if (photo.indexOf("quotes/") !== 0 || photo.indexOf("..") !== -1) {
      return new Response("Bad Request", { status: 400 });
    }
    const obj = await env.QUOTE_PHOTOS.get(photo);
    if (!obj) return new Response("Not Found", { status: 404 });
    return new Response(obj.body, {
      headers: {
        "content-type": (obj.httpMetadata && obj.httpMetadata.contentType) || "application/octet-stream",
        "cache-control": "private, no-store",
      },
    });
  }

  if (!env.WAITLIST) return json({ ok: true, count: 0, quotes: [] });

  const quotes = [];
  let cursor;
  do {
    const page = await env.WAITLIST.list({ prefix: "quote:", cursor: cursor });
    for (const k of page.keys) {
      const v = await env.WAITLIST.get(k.name);
      if (v) {
        try { quotes.push(JSON.parse(v)); } catch (e) { /* skip bad row */ }
      }
    }
    cursor = page.list_complete ? undefined : page.cursor;
  } while (cursor);
  quotes.sort(function (a, b) { return a.ts < b.ts ? 1 : -1; });
  return json({ ok: true, count: quotes.length, quotes: quotes });
}
