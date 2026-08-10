// Unit tests for the Cloudflare Pages Functions in functions/api/.
//
// These 666 lines run on the public internet and had no test coverage at all.
// There is no JS test runner in this repo and adding one is not worth it for
// three files, so this is a plain Node script: it exits non-zero on failure and
// tests/test_functions_js.py runs it as part of the normal pytest suite.
//
// Node 22 provides Request/Response/URL/TextEncoder/crypto globally, which is
// close enough to the Workers runtime for this code.

import { onRequestPost as waitlistPost, onRequestGet as waitlistGet }
  from "../functions/api/waitlist.js";
import { onRequestPost as contactPost, onRequestGet as contactGet }
  from "../functions/api/contact.js";
import { onRequestPost as quotePost, onRequestGet as quoteGet }
  from "../functions/api/quote.js";
import { timingSafeEqual, isAllowedOrigin, exportRecords, fitsMetadata }
  from "../functions/api/_shared.js";

let failures = 0;
function check(name, cond, detail) {
  if (cond) { console.log(`  ok   ${name}`); }
  else { failures++; console.log(`  FAIL ${name}${detail ? " — " + detail : ""}`); }
}
async function eq(name, actual, expected) {
  check(name, actual === expected, `got ${JSON.stringify(actual)}, want ${JSON.stringify(expected)}`);
}

// ── Fakes ──────────────────────────────────────────────────────────────────
class FakeKV {
  constructor() { this.store = new Map(); this.gets = 0; this.puts = 0; this.lists = 0; }
  async get(k) { this.gets++; const e = this.store.get(k); return e ? e.value : null; }
  async put(k, v, opts) {
    this.puts++;
    this.store.set(k, { value: v, metadata: (opts && opts.metadata) || null });
  }
  async list({ prefix, cursor, limit }) {
    this.lists++;
    const all = [...this.store.keys()].filter((k) => k.startsWith(prefix)).sort();
    const start = cursor ? Number(cursor) : 0;         // opaque to callers
    const lim = limit || 1000;
    const slice = all.slice(start, start + lim);
    const end = start + slice.length;
    return {
      keys: slice.map((name) => ({ name, metadata: this.store.get(name).metadata })),
      list_complete: end >= all.length,
      cursor: end >= all.length ? undefined : String(end),
    };
  }
}
const req = (url, { method = "POST", origin = "https://datumlaboratories.com", body, json = true } = {}) => {
  const headers = {};
  if (origin) headers["origin"] = origin;
  if (json && body !== undefined) headers["content-type"] = "application/json";
  return new Request(url, {
    method,
    headers,
    body: body === undefined ? undefined : (json ? JSON.stringify(body) : body),
  });
};
const parse = async (res) => { try { return await res.json(); } catch (e) { return null; } };

// ── timingSafeEqual ────────────────────────────────────────────────────────
console.log("timingSafeEqual");
check("equal strings match", timingSafeEqual("hunter2", "hunter2"));
check("different strings differ", !timingSafeEqual("hunter2", "hunter3"));
check("prefix is not a match", !timingSafeEqual("hunt", "hunter2"));
check("empty vs non-empty differ", !timingSafeEqual("", "x"));
check("null-safe", !timingSafeEqual(null, "x"));
// A multi-byte char must not collapse to the same length as its ASCII count.
check("compares UTF-8 bytes, not code units", !timingSafeEqual("é", "e"));

// ── isAllowedOrigin ────────────────────────────────────────────────────────
console.log("isAllowedOrigin");
const hosts = ["datumlaboratories.com", "abc.datumlaboratories-git.pages.dev"];
check("own origin allowed",
  isAllowedOrigin(new Request("https://x/", { headers: { origin: "https://datumlaboratories.com" } }), hosts));
check("subdomain allowed",
  isAllowedOrigin(new Request("https://x/", { headers: { origin: "https://www.datumlaboratories.com" } }), hosts));
check("preview deploy allowed",
  isAllowedOrigin(new Request("https://x/", { headers: { origin: "https://abc.datumlaboratories-git.pages.dev" } }), hosts));
check("foreign origin rejected",
  !isAllowedOrigin(new Request("https://x/", { headers: { origin: "https://evil.example" } }), hosts));
check("no origin and no referer rejected",
  !isAllowedOrigin(new Request("https://x/"), hosts));
check("referer used when origin absent",
  isAllowedOrigin(new Request("https://x/", { headers: { referer: "https://datumlaboratories.com/services" } }), hosts));
// A host that merely ends with the string must not pass.
check("lookalike host rejected",
  !isAllowedOrigin(new Request("https://x/", { headers: { origin: "https://notdatumlaboratories.com" } }), hosts));

// ── waitlist POST ──────────────────────────────────────────────────────────
console.log("waitlist POST");
{
  const env = { WAITLIST: new FakeKV() };
  let r = await waitlistPost({ request: req("https://datumlaboratories.com/api/waitlist",
    { origin: "https://evil.example", body: { email: "a@b.co" } }), env });
  await eq("foreign origin -> 403", r.status, 403);
  await eq("foreign origin wrote nothing", env.WAITLIST.puts, 0);

  r = await waitlistPost({ request: req("https://datumlaboratories.com/api/waitlist",
    { body: { email: "not-an-email" } }), env });
  await eq("invalid email -> 422", r.status, 422);

  r = await waitlistPost({ request: req("https://datumlaboratories.com/api/waitlist",
    { body: { email: "bot@b.co", company: "AcmeCorp" } }), env });
  await eq("honeypot -> 200", r.status, 200);
  await eq("honeypot stored nothing", env.WAITLIST.puts, 0);

  r = await waitlistPost({ request: req("https://datumlaboratories.com/api/waitlist",
    { body: { email: "real@b.co" } }), env });
  await eq("valid signup -> 200", r.status, 200);
  await eq("valid signup stored", env.WAITLIST.puts, 1);
  const entry = env.WAITLIST.store.get("signup:real@b.co");
  check("record written to metadata (so export needs no get)",
    entry.metadata && entry.metadata.email === "real@b.co");

  const before = env.WAITLIST.puts;
  r = await waitlistPost({ request: req("https://datumlaboratories.com/api/waitlist",
    { body: { email: "REAL@b.co" } }), env });
  check("duplicate is idempotent", (await parse(r)).duplicate === true);
  await eq("duplicate wrote nothing", env.WAITLIST.puts, before);
}

// ── contact POST ───────────────────────────────────────────────────────────
console.log("contact POST");
{
  const env = { WAITLIST: new FakeKV() };
  const good = { email: "a@b.co", message: "hello there", name: "A", service: "Embedded" };
  let r = await contactPost({ request: req("https://datumlaboratories.com/api/contact", { body: good }), env });
  await eq("first inquiry -> 200", r.status, 200);

  r = await contactPost({ request: req("https://datumlaboratories.com/api/contact", { body: good }), env });
  await eq("second inquiry from same email -> 429", r.status, 429);
  const puts = env.WAITLIST.puts;
  await contactPost({ request: req("https://datumlaboratories.com/api/contact", { body: good }), env });
  await eq("throttled attempts cost no writes", env.WAITLIST.puts, puts);

  r = await contactPost({ request: req("https://datumlaboratories.com/api/contact",
    { body: { ...good, email: "c@d.co", company: "x" } }), env });
  check("honeypot accepted but discarded", r.status === 200 && env.WAITLIST.puts === puts);

  r = await contactPost({ request: req("https://datumlaboratories.com/api/contact",
    { body: { email: "e@f.co", message: "" } }), env });
  await eq("empty message -> 422", r.status, 422);
}

// ── export: the subrequest bug this whole change exists for ───────────────
console.log("export");
{
  // 300 modern records, all carrying metadata. The old handler issued one get()
  // per key and died at the 50-subrequest cap; this must read them all.
  const kv = new FakeKV();
  for (let i = 0; i < 300; i++) {
    const rec = { email: `u${i}@b.co`, ts: `2026-08-04T00:00:${String(i % 60).padStart(2, "0")}Z` };
    await kv.put(`signup:u${i}@b.co`, JSON.stringify(rec), { metadata: rec });
  }
  kv.gets = 0; kv.lists = 0;
  const out = await exportRecords({ WAITLIST: kv }, "signup:", {});
  await eq("all 300 metadata records returned", out.records.length, 300);
  await eq("zero get() subrequests spent", kv.gets, 0);
  check("stayed within the subrequest budget", kv.lists + kv.gets <= 40, `${kv.lists} lists`);
  check("not truncated", out.truncated === false);

  // Legacy records (written before metadata) still need a get each, so the
  // export must page rather than blow the budget — and the cursor it hands back
  // has to be one KV itself produced, not a key name.
  const kv2 = new FakeKV();
  for (let i = 0; i < 200; i++) {
    await kv2.put(`signup:v${String(i).padStart(3, "0")}@b.co`,
      JSON.stringify({ email: `v${i}@b.co`, ts: "2026-08-04T00:00:00Z" }));  // no metadata
  }
  kv2.gets = 0; kv2.lists = 0;
  const p1 = await exportRecords({ WAITLIST: kv2 }, "signup:", {});
  check("legacy export truncates instead of exceeding budget", p1.truncated === true);
  check("stayed within budget", kv2.lists + kv2.gets <= 40, `${kv2.lists} lists + ${kv2.gets} gets`);
  check("returned a resumable cursor", typeof p1.cursor === "string" && p1.cursor.length > 0);
  const p2 = await exportRecords({ WAITLIST: kv2 }, "signup:", { cursor: p1.cursor });
  check("cursor resumes and yields new records", p2.records.length > 0);
  const overlap = p1.records.filter((a) => p2.records.some((b) => b.email === a.email));
  await eq("pages do not overlap", overlap.length, 0);
}

// ── export auth ────────────────────────────────────────────────────────────
console.log("export auth");
{
  const kv = new FakeKV();
  let r = await waitlistGet({ request: new Request("https://x/api/waitlist"), env: { WAITLIST: kv } });
  await eq("no token secret set -> 405", r.status, 405);
  r = await waitlistGet({ request: new Request("https://x/api/waitlist?token=wrong"),
    env: { WAITLIST: kv, WAITLIST_TOKEN: "right" } });
  await eq("wrong token -> 403", r.status, 403);
  r = await waitlistGet({ request: new Request("https://x/api/waitlist?token=right"),
    env: { WAITLIST: kv, WAITLIST_TOKEN: "right" } });
  await eq("correct token -> 200", r.status, 200);
  r = await contactGet({ request: new Request("https://x/api/contact?token=wrong"),
    env: { WAITLIST: kv, WAITLIST_TOKEN: "right" } });
  await eq("contact export honours the same token", r.status, 403);

  r = await quoteGet({ request: new Request("https://x/api/quote"), env: { WAITLIST: kv } });
  await eq("quote export with no token secret set -> 405", r.status, 405);
  r = await quoteGet({ request: new Request("https://x/api/quote?token=right"),
    env: { WAITLIST: kv, WAITLIST_TOKEN: "right" } });
  await eq("quote export accepts correct token", r.status, 200);
  r = await quoteGet({ request: new Request("https://x/api/quote?token=wrong"),
    env: { WAITLIST: kv, WAITLIST_TOKEN: "right" } });
  await eq("quote export rejects incorrect token", r.status, 403);
  r = await quoteGet({ request: new Request("https://x/api/quote"),
    env: { WAITLIST: kv, WAITLIST_TOKEN: "right" } });
  await eq("quote export rejects missing token", r.status, 403);
  r = await quoteGet({ request: new Request("https://x/api/quote?token=r%C3%AFght"),
    env: { WAITLIST: kv, WAITLIST_TOKEN: "right" } });
  await eq("quote export rejects non-ASCII token", r.status, 403);
}

// ── quote POST ─────────────────────────────────────────────────────────────
// This endpoint accepts 20 MB of photos and writes to R2, KV and Resend, and it
// had NEITHER of the two guards its siblings have — its only protection was a
// rate limiter that fails open by design. The honeypot field has shipped on
// site/replacement-parts.html all along; the server never read it.
console.log("quote POST");
{
  const env = { WAITLIST: new FakeKV() };

  function multipart(fields) {
    const fd = new FormData();
    for (const [k, v] of Object.entries(fields)) fd.append(k, v);
    return fd;
  }
  function quoteReq(fields, headers) {
    return new Request("https://datumlaboratories.com/api/quote", {
      method: "POST", body: multipart(fields),
      headers: Object.assign({ origin: "https://datumlaboratories.com" }, headers || {}),
    });
  }

  let r = await quotePost({
    request: quoteReq({ name: "A", shop: "S", email: "a@b.co" },
                      { origin: "https://evil.example" }), env });
  await eq("foreign origin -> 403", r.status, 403);
  await eq("foreign origin wrote nothing", env.WAITLIST.puts, 0);

  r = await quotePost({
    request: quoteReq({ name: "A", shop: "S", email: "a@b.co", company: "AcmeCorp" }), env });
  await eq("honeypot -> 200", r.status, 200);
  await eq("honeypot stored nothing", env.WAITLIST.puts, 0);

  // ...and the honeypot must be checked BEFORE validation, or a bot learns
  // which of its fields were wrong.
  r = await quotePost({
    request: quoteReq({ name: "", shop: "", email: "nope", company: "AcmeCorp" }), env });
  await eq("honeypot short-circuits validation", r.status, 200);

  r = await quotePost({
    request: quoteReq({ name: "A", shop: "S", email: "not-an-email" }), env });
  await eq("same-origin submission reaches validation", r.status, 422);
}

// ── a quote export must not be lossy ───────────────────────────────────────
// exportRecords returns KV metadata VERBATIM whenever it carries an `email`,
// so writing a hand-built summary there makes the export free and silently
// incomplete: the customer's description, the referrer, the CamScan bundle and
// the per-photo details all stop being exported, and `photos` turns from an
// array of objects into an integer.
console.log("quote export completeness");
{
  const env = { WAITLIST: new FakeKV(), WAITLIST_TOKEN: "right" };
  const fd = new FormData();
  fd.append("name", "A"); fd.append("shop", "S"); fd.append("email", "a@b.co");
  fd.append("description", "x".repeat(1200));
  const png = new Uint8Array(64);
  png.set([0x89, 0x50, 0x4E, 0x47, 0x0D, 0x0A, 0x1A, 0x0A], 0);
  fd.append("photos", new File([png], "p.png", { type: "image/png" }));
  const r = await quotePost({
    request: new Request("https://datumlaboratories.com/api/quote", {
      method: "POST", body: fd,
      headers: { origin: "https://datumlaboratories.com" } }), env });
  await eq("submission stored", (await parse(r)).stored, true);

  const g = await quoteGet({
    request: new Request("https://x/api/quote?token=right"), env });
  const body = await parse(g);
  await eq("one quote exported", body.count, 1);
  const q = body.quotes[0];
  check("the description survives the round trip",
    q.description && q.description.length === 1200,
    `got ${JSON.stringify(q.description || "").slice(0, 40)}`);
  check("photos is still an array of objects, not a count",
    Array.isArray(q.photos) && q.photos.length === 1 && !!q.photos[0].filename,
    JSON.stringify(q.photos));
}

// ── quote export stays inside the subrequest budget ────────────────────────
// A Worker invocation is capped at 50 subrequests on the free plan. The old
// hand-rolled loop issued one KV.get() per key, so the export worked in testing
// and started throwing at roughly 49 stored quotes.
console.log("quote export");
{
  const kv = new FakeKV();
  for (let i = 0; i < 120; i++) {
    const ts = `2026-08-${String((i % 28) + 1).padStart(2, "0")}T00:00:00.000Z`;
    await kv.put(`quote:${ts}:${i}`, JSON.stringify({ ts, email: `a${i}@b.co` }),
                 { metadata: { kind: "replacement_part", email: `a${i}@b.co`, ts } });
  }
  kv.gets = 0; kv.lists = 0;
  const r = await quoteGet({
    request: new Request("https://x/api/quote?token=right"),
    env: { WAITLIST: kv, WAITLIST_TOKEN: "right" } });
  const body = await parse(r);
  await eq("120 stored quotes still export", r.status, 200);
  await eq("metadata rows cost no gets", kv.gets, 0);
  check("subrequests stay under the 50-per-invocation cap",
    kv.gets + kv.lists < 50, `used ${kv.gets + kv.lists}`);
  await eq("every record returned", body.count, 120);
}

// ── fitsMetadata ───────────────────────────────────────────────────────────
console.log("fitsMetadata");
check("small record fits", fitsMetadata({ email: "a@b.co", ts: "x" }) !== null);
check("oversized record rejected (KV caps metadata at 1 KiB)",
  fitsMetadata({ email: "a@b.co", message: "x".repeat(5000) }) === null);

console.log(failures === 0 ? "\nALL PASS" : `\n${failures} FAILURE(S)`);
process.exit(failures === 0 ? 0 : 1);
