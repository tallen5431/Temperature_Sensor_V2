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
