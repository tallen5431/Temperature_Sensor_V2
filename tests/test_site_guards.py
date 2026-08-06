"""Guards for site/ — the marketing site's two load-bearing rules, enforced.

site/README.md states both as prose. Prose did not hold them:

1. "Assembled units may not be offered for sale until the FCC Part 15B SDoC is
   complete... Any copy implying an assembled unit is purchasable is a
   compliance problem, not just a wording one." pilot.html step 04 nevertheless
   read "If you want to keep it we quote a buy-once price for the probes",
   contradicting its own footer twelve lines later ("supplied as loaner
   evaluation equipment... they are not sold").

2. "pilot.html and docs/PILOT_OFFER.md carry the same offer and a customer may
   read both. Change them together." Both carried the same sale offer, so the
   pairing rule held while the compliance rule broke — the documents agreed
   with each other and disagreed with the policy.

Plus a regression test for the ROI calculator, whose render() deleted the
element ids it needed on the first pass.
"""
import pathlib
import re

import pytest

REPO = pathlib.Path(__file__).resolve().parent.parent
SITE = REPO / "site"

# Phrases that constitute an OFFER to sell an assembled unit. Deliberately
# narrow: describing a future pricing MODEL ("when they are available, buy
# once") is allowed and commercially useful — quoting a price for one today is
# not. Keep this list tight; a broad match would fire on the DIY kit, which is
# genuinely for sale.
SALE_OFFER_PATTERNS = [
    r"\bbuy-once price\b",
    r"\bbuy-the-probes-once\b",
    r"\bquote a buy\b",
    r"\bbuy the probes\b",
    r"\bprice for the probes\b",
]

# The pilot funnel — the pages where an assembled unit is physically in the
# customer's hands, so where a sale offer is most tempting and most costly.
PILOT_FUNNEL = [SITE / "pilot.html", REPO / "docs" / "PILOT_OFFER.md"]


@pytest.mark.parametrize("path", PILOT_FUNNEL, ids=lambda p: p.name)
def test_no_offer_to_sell_an_assembled_unit(path):
    text = path.read_text(encoding="utf-8")
    hits = [p for p in SALE_OFFER_PATTERNS if re.search(p, text, re.I)]
    assert not hits, (
        f"{path.relative_to(REPO)} appears to offer an assembled unit for sale "
        f"({hits}). site/README.md rule 1: only the DIY kit and the free loaner "
        f"pilot may be marketed until the FCC Part 15B SDoC is complete.")


def test_the_pilot_page_and_the_pilot_doc_still_agree():
    """README rule 2 — a customer may read both, so they must not diverge on
    whether the probes are returned. This checks the FACT they must share, not
    their wording, which is deliberately different (one is a web page)."""
    page = (SITE / "pilot.html").read_text(encoding="utf-8").lower()
    doc = (REPO / "docs" / "PILOT_OFFER.md").read_text(encoding="utf-8").lower()
    for name, text in (("pilot.html", page), ("PILOT_OFFER.md", doc)):
        assert "loaner" in text, f"{name} no longer says the probes are loaner equipment"
        assert "fcc" in text, (
            f"{name} no longer explains WHY the probes come back. Without the "
            f"reason it reads as a restriction rather than a temporary one.")


def test_pilot_page_does_not_contradict_its_own_footer():
    """The defect was self-contradiction, not just policy: step 04 offered a
    sale while the fineprint said 'they are not sold'."""
    page = (SITE / "pilot.html").read_text(encoding="utf-8")
    assert "are not sold" in page, "the loaner fineprint disappeared from pilot.html"
    body = page.split('class="fineprint"')[0]        # everything above the disclaimer
    assert not re.search(r"buy-once|buy the probes", body, re.I), \
        "pilot.html body offers a sale that its own fineprint denies"


def _script_of(path):
    html = path.read_text(encoding="utf-8")
    return html, "\n".join(re.findall(r"<script[^>]*>(.*?)</script>", html, re.S))


@pytest.mark.parametrize(
    "path",
    [SITE / "roi-calculator.html", REPO / "docs" / "roi-calculator.html"],
    ids=["site", "docs"],
)
def test_roi_calculator_never_destroys_the_ids_it_updates(path):
    """render() rewrote #r_frame with innerHTML and only re-added SOME of the
    ids inside it. id="f_cost" was dropped, so the second render threw on
    $("f_cost").textContent and every later update died there — while the
    payback figures ABOVE it, set before the throw, kept moving. The page then
    showed two different system costs at once and asserted the first cooler
    "more than pays for the whole system" when the numbers said otherwise."""
    html, script = _script_of(path)

    assert "r_frame" not in re.findall(r"(\w+)\.innerHTML\s*=", script) and \
        not re.search(r'\$\("r_frame"\)\.innerHTML\s*=|frame\.innerHTML\s*=', script), \
        "#r_frame is being rewritten wholesale again — that is what deleted the ids"

    # Every id the script writes to must exist in the STATIC markup, so it is
    # there on the first render and every render after it.
    static_ids = set(re.findall(r'id="([A-Za-z0-9_]+)"', html))
    written = set(re.findall(r'\$\("([A-Za-z0-9_]+)"\)\.(?:textContent|innerHTML|style)', script))
    missing = sorted(written - static_ids)
    assert not missing, f"{path.name}: script writes to ids absent from the markup: {missing}"


# --- navigation ------------------------------------------------------------
# The site grew by accretion over eleven days and each new page copied whichever
# page was nearest, so four different nav link-sets ended up in circulation and
# /pilot -- the README's "highest-value offer available today" -- was in none of
# them. These pin the shape so it cannot drift apart again.

SETPOINT_PAGES = ["index.html", "pilot.html", "walk-in-cooler.html", "freezer-alarm.html"]
REPORT_PAGES = ["field-test.html", "roi-calculator.html"]


def _hrefs(html, nav_class):
    m = re.search(rf'<nav class="{nav_class}"[^>]*>(.*?)</nav>', html, re.S)
    assert m, f"no nav.{nav_class} found"
    return re.findall(r'href="([^"]+)"', m.group(1))


def test_every_setpoint_page_offers_the_same_destinations():
    """Desktop and mobile must agree, and all four pages must agree with each
    other. Only the trailing per-page CTA may differ."""
    seen = {}
    for name in SETPOINT_PAGES:
        html = (SITE / name).read_text(encoding="utf-8")
        top, mob = _hrefs(html, "top"), _hrefs(html, "mobile-menu")
        assert top == mob, f"{name}: desktop and mobile navs disagree\n{top}\n{mob}"
        seen[name] = top[:-1]          # drop the CTA, which is page-specific
    routes = list(seen.values())
    assert all(r == routes[0] for r in routes), f"nav link-sets diverged: {seen}"


def test_no_setpoint_nav_uses_a_cross_page_anchor():
    """`/#how` and `/#specs` looked like section jumps and were full navigations
    to another document. On pilot.html the styled nav button was `/#reserve`,
    which lands on the homepage section headed "Get an assembled unit first." —
    the wrong offer, on the wrong page, from the site's best page."""
    for name in SETPOINT_PAGES + REPORT_PAGES:
        html = (SITE / name).read_text(encoding="utf-8")
        assert not re.search(r'href="/#', html), \
            f"{name} still routes to a homepage anchor from a subpage"


@pytest.mark.parametrize("name", SETPOINT_PAGES + REPORT_PAGES)
def test_pilot_is_reachable_from_every_setpoint_page(name):
    html = (SITE / name).read_text(encoding="utf-8")
    assert 'href="/pilot"' in html, (
        f"{name} has no link to /pilot. site/README.md calls it the "
        f"highest-value offer available today; it was previously in no <nav> "
        f"on any page and linked from only two files.")


def test_every_internal_link_and_anchor_resolves():
    pages = {p.name: p.read_text(encoding="utf-8") for p in SITE.glob("*.html")}
    ids = {n: set(re.findall(r'id="([A-Za-z0-9_-]+)"', s)) for n, s in pages.items()}
    by_route = {"/" + ("" if n == "index.html" else n[:-5]): n for n in pages}
    bad = []
    for name, s in pages.items():
        for href in re.findall(r'href="([^"]+)"', s):
            if href.startswith(("http", "mailto:", "tel:", "data:", "//")) or "+" in href:
                continue                      # last clause skips JS-built hrefs
            path, _, frag = href.partition("#")
            target = name if not path else by_route.get(path.rstrip("/") or "/")
            if path and target is None:
                bad.append(f"{name} -> {href} (no such page)")
            elif frag and frag not in ids.get(target, set()):
                bad.append(f"{name} -> {href} (no id '{frag}' in {target})")
    assert not bad, "broken internal links:\n  " + "\n  ".join(bad)


def test_every_assembled_tier_says_it_is_not_yet_for_sale():
    """site/README.md rule 1 applies to BOTH assembled tiers, not just one.
    "Setpoint Battery" carried "not yet for sale" while its neighbour "Setpoint
    USB" -- the same Rev 2 board, mains-powered -- was priced and spec'd as
    assembled with no qualifier at all. The DIY kit is genuinely purchasable and
    is deliberately excluded."""
    html = (SITE / "index.html").read_text(encoding="utf-8")
    tiers = re.findall(r'<div class="badge">([^<]*)</div>\s*<h3>([^<]*)</h3>', html)
    assert tiers, "tier markup changed shape — update this test"
    for badge, name in tiers:
        if "DIY" in name:
            assert "available now" in badge, f"{name}: the kit IS for sale, say so"
        else:
            assert "not yet for sale" in badge, (
                f'"{name}" is an assembled unit priced on the page with badge '
                f'"{badge}" and no availability qualifier. Assembled units may '
                f"not be offered for sale until the FCC Part 15B SDoC is done.")


SETUP_SITE = "setpoint.datumlaboratories.com"


@pytest.mark.parametrize(
    "name", sorted(p.name for p in (pathlib.Path(__file__).resolve().parent.parent
                                    / "site").glob("*.html")))
def test_every_page_can_reach_the_setup_site(name):
    """setpoint.datumlaboratories.com is where a buyer downloads the launcher,
    flashes the probe in the browser and follows the build guide -- the entire
    post-purchase path.

    A nav rebuild dropped the "Setup" link on the grounds that post-purchase
    support did not need prime nav space, and the footer link that was supposed
    to replace it never got added. The result shipped: ZERO links to the setup
    site anywhere on the marketing site, so nobody who bought a kit could find
    the flasher from datumlaboratories.com. Every page needs a route."""
    html = (SITE / name).read_text(encoding="utf-8")
    assert SETUP_SITE in html, (
        f"{name} has no link to {SETUP_SITE} — kit buyers reach the flasher, "
        f"the launcher download and the build guide through it.")


# --- what a customer sees BEFORE the site ----------------------------------
# The title and meta description are the search result and the link preview —
# often the first impression, and the only one for anyone who does not click.
# Every page's description was 180-252 characters against the ~155 Google
# renders, so every snippet ended mid-sentence, and 404.html had none at all.

import html as _html

SEO_PAGES = sorted(p.name for p in SITE.glob("*.html"))
DESC_MAX = 160      # Google renders ~155; 160 is the usual working budget
TITLE_MAX = 60


def _head(name):
    s = (SITE / name).read_text(encoding="utf-8")
    title = _html.unescape((re.search(r"<title>(.*?)</title>", s, re.S) or [None, ""])[1].strip())
    m = re.search(r'<meta name="description" content="([^"]*)"', s)
    return title, (_html.unescape(m.group(1)) if m else None)


@pytest.mark.parametrize("name", SEO_PAGES)
def test_every_page_has_a_description_that_fits(name):
    """Measured on the RENDERED text, not the source: `&mdash;` is seven
    characters in the file and one on the page, so counting the source
    over-reports and would have had me shortening titles that were already
    fine."""
    _title, desc = _head(name)
    assert desc, f"{name} has no meta description — search engines invent one"
    assert len(desc) <= DESC_MAX, (
        f"{name}: {len(desc)} chars, so the snippet is cut mid-sentence at ~155")


@pytest.mark.parametrize("name", SEO_PAGES)
def test_every_page_title_fits(name):
    title, _desc = _head(name)
    assert title, f"{name} has no <title>"
    assert len(title) <= TITLE_MAX, f"{name}: {len(title)} chars, truncates at ~60"


@pytest.mark.parametrize("name", SEO_PAGES)
def test_no_two_pages_share_a_description(name):
    """Duplicate descriptions across pages are a ranking problem and read as
    boilerplate to anyone comparing two results."""
    _t, desc = _head(name)
    others = {n: _head(n)[1] for n in SEO_PAGES if n != name}
    clash = [n for n, d in others.items() if d and d == desc]
    assert not clash, f"{name} shares its description with {clash}"


def test_the_assembled_tiers_say_why_they_cannot_be_bought():
    """site/README.md rule 1 makes "not yet for sale" mandatory on the assembled
    tiers. The REASON lived only in the CTA band ~2000px below the pricing
    cards, so the section stated a restriction and gave no cause for it — and a
    reason that specific (FCC Part 15B testing underway) reads as diligence
    rather than as a limitation."""
    html_text = (SITE / "index.html").read_text(encoding="utf-8")
    whys = re.findall(r'<div class="tier-why">(.*?)</div>', html_text, re.S)
    assert len(whys) == 2, (
        f"expected the explanation on both assembled tiers, found {len(whys)}")
    for w in whys:
        assert "FCC" in w and "15B" in w, "the reason no longer names the actual cause"
