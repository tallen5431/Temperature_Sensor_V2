// Shared helpers for the Pages Functions in this directory.
//
// Cloudflare Pages does NOT route files whose name starts with `_`, so this is
// a module, not an endpoint. waitlist.js and contact.js both import from it;
// quote.js keeps its own copies because its needs (image sniffing, EXIF
// stripping, HTML escaping for the notification email) are its own.

export function json(body, status) {
  return new Response(JSON.stringify(body), {
    status: status || 200,
    headers: { "content-type": "application/json; charset=utf-8" },
  });
}

export function clip(v, max) {
  return String(v == null ? "" : v).trim().slice(0, max);
}

// Constant-time string comparison for the export token.
//
// `a !== b` returns as soon as it finds a differing byte, so how long it takes
// leaks how many leading characters were right. That is the same reason the hub
// uses core/secret_compare.constant_time_eq() and SECURITY.md states "Token
// comparison is constant-time" — this keeps the public-facing endpoints to the
// standard the rest of the project already holds.
//
// Compares UTF-8 bytes, not UTF-16 code units, so a multi-byte character cannot
// make two different tokens compare equal by length alone.
export function timingSafeEqual(a, b) {
  const enc = new TextEncoder();
  const x = enc.encode(String(a == null ? "" : a));
  const y = enc.encode(String(b == null ? "" : b));
  // Length is not secret (it is visible in the request), but the loop must still
  // run a fixed number of times for a given input, so fold length into the diff
  // instead of returning early.
  let diff = x.length ^ y.length;
  const n = Math.max(x.length, y.length);
  for (let i = 0; i < n; i++) {
    diff |= (x[i] === undefined ? 0 : x[i]) ^ (y[i] === undefined ? 0 : y[i]);
  }
  return diff === 0;
}

// Reject writes that did not come from our own pages.
//
// This is not authentication — an Origin header is trivially forged by anything
// that is not a browser. It exists to stop the drive-by case: a scraper or a
// naive script POSTing in a loop, which on the free KV plan (1,000 writes/day)
// silently exhausts the quota and makes real submissions start failing. Genuine
// rate limiting belongs in a Cloudflare WAF rule; see site/README.md.
//
// Same-origin browser POSTs from our own forms always carry Origin. A missing
// Origin is allowed only when Referer matches, which covers older browsers and
// direct form posts without opening it to header-less bots.
export function isAllowedOrigin(request, allowedHosts) {
  const hosts = allowedHosts && allowedHosts.length ? allowedHosts : [];
  const hostOf = (u) => { try { return new URL(u).host.toLowerCase(); } catch (e) { return ""; } };
  const origin = request.headers.get("origin") || "";
  const referer = request.headers.get("referer") || "";
  const candidate = origin ? hostOf(origin) : hostOf(referer);
  if (!candidate) return false;
  return hosts.some((h) => candidate === h || candidate.endsWith("." + h));
}

export function allowedHostsFor(request, env) {
  const own = (() => { try { return new URL(request.url).host.toLowerCase(); } catch (e) { return ""; } })();
  const extra = String(env && env.ALLOWED_ORIGIN_HOSTS ? env.ALLOWED_ORIGIN_HOSTS : "")
    .split(",").map((s) => s.trim().toLowerCase()).filter(Boolean);
  // `own` covers both the custom domain and any *.pages.dev preview deployment,
  // so previews keep working without extra configuration.
  return [own, "datumlaboratories.com", ...extra].filter(Boolean);
}

// Paginated, metadata-aware KV export.
//
// The bug this replaces: the old handlers walked every key and issued a
// KV.get() for each one. Every get is a subrequest, and a Worker invocation is
// capped at 50 subrequests on the free plan — so the export worked in testing
// and started failing at roughly 50 records, which is exactly the point where
// the list becomes worth exporting.
//
// Two changes fix it. New records carry their payload in KV metadata, which
// list() returns inline for free, so they cost no subrequests at all. Records
// written before that (or too large for the 1 KiB metadata limit) still need a
// get(), so those are spent against an explicit budget and the handler returns
// a cursor rather than blowing the limit.
export const SUBREQUEST_BUDGET = 40;   // of 50 on the free plan; headroom left over

export async function exportRecords(env, prefix, opts) {
  const o = opts || {};
  const budget = o.budget || SUBREQUEST_BUDGET;
  const records = [];
  let cursor = o.cursor || undefined;
  let ops = 0;                 // every KV list AND get is a subrequest
  let truncated = false;

  while (true) {
    // Bound the page to what the remaining budget could pay for if every key on
    // it turned out to be a legacy record needing a get(). That is what makes
    // truncation land on a page boundary: `cursor` must be an opaque value from
    // a previous list(), so stopping mid-page would leave nothing valid to
    // resume from. (-1 pays for this list call itself.)
    const room = budget - ops - 1;
    if (room < 1) { truncated = true; break; }
    const page = await env.WAITLIST.list({
      prefix: prefix, cursor: cursor, limit: Math.min(1000, room),
    });
    ops++;
    for (const k of page.keys) {
      if (k.metadata && typeof k.metadata === "object" && k.metadata.email) {
        records.push(k.metadata);              // free — came back with list()
        continue;
      }
      ops++;                                   // legacy record: costs a get
      const v = await env.WAITLIST.get(k.name);
      if (v) { try { records.push(JSON.parse(v)); } catch (e) { /* skip bad row */ } }
    }
    cursor = page.list_complete ? undefined : page.cursor;
    if (!cursor) break;
  }

  records.sort((a, b) => (a.ts < b.ts ? 1 : -1));
  return { records, truncated, cursor: truncated ? cursor : undefined };
}

// KV metadata is capped at 1024 bytes. Return the record if it fits, else null
// so the caller falls back to storing it in the value only.
export function fitsMetadata(record) {
  try {
    return new TextEncoder().encode(JSON.stringify(record)).length <= 1024 ? record : null;
  } catch (e) {
    return null;
  }
}
