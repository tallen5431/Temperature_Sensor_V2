#!/usr/bin/env python3
"""Generate THIRD-PARTY-LICENSES.md from the installed runtime dependencies.

Run from the repo root in the SAME environment used to build the shipped product
(so the dependency versions match what PyInstaller bundles):

    python packaging/gen_third_party_licenses.py

It walks the runtime requirement tree, records each package's version, license,
and project URL, and appends the full text of each package's bundled license
file.  Firmware libraries and the LGPL source-offer are added as fixed sections.
"""
from __future__ import annotations

import importlib.metadata as im
import re
from datetime import date
from pathlib import Path, PurePosixPath

# The hub's direct runtime dependencies (see requirements.txt).
DIRECT = ["dash", "dash-bootstrap-components", "pandas", "plotly", "requests",
          "zeroconf", "waitress"]

# Firmware libraries are not pip packages — list them by hand (verify each in the
# Arduino Library Manager; LGPL ones carry the same obligations as zeroconf).
FIRMWARE = [
    ("Arduino core for ESP32", "Espressif", "LGPL-2.1 / Apache-2.0",
     "https://github.com/espressif/arduino-esp32"),
    ("WiFiManager", "tzapu", "MIT", "https://github.com/tzapu/WiFiManager"),
    ("ArduinoJson", "Benoit Blanchon", "MIT", "https://github.com/bblanchon/ArduinoJson"),
    ("DallasTemperature", "Miles Burton", "LGPL-2.1", "https://github.com/milesburton/Arduino-Temperature-Control-Library"),
    ("OneWire", "Paul Stoffregen et al.", "MIT-style (permissive)", "https://github.com/PaulStoffregen/OneWire"),
]

LGPL_NOTICE = """\
## LGPL components — source offer

This product includes components licensed under the **GNU Lesser General Public
License v2.1 (LGPL-2.1)**. You may obtain, modify, and relink these components.
Their complete corresponding source is available at the URLs below (pinned to
the version distributed with this product); we will also provide it on request.

| Component | Where it runs | Source |
|---|---|---|
| `zeroconf` (python-zeroconf) | Hub | https://github.com/python-zeroconf/python-zeroconf |
| `DallasTemperature` | Probe firmware | https://github.com/milesburton/Arduino-Temperature-Control-Library |
| Arduino core for ESP32 | Probe firmware | https://github.com/espressif/arduino-esp32 |

The hub is distributed as a PyInstaller **onedir** bundle: the LGPL Python
module files live under `_internal/` in the distribution folder and may be
replaced with a user-modified build. The full text of the LGPL-2.1 is available
at https://www.gnu.org/licenses/old-licenses/lgpl-2.1.txt and is reproduced with
each LGPL component below where the package ships it.
"""


def _norm(name: str) -> str:
    return re.sub(r"[-_.]+", "-", (name or "").strip()).lower()


def _dep_name(req: str) -> str:
    head = req.split(";", 1)[0]
    return re.split(r"[<>=!~ ;\[(]", head, 1)[0].strip()


def closure(direct):
    """Return {normalized_name: Distribution} for the installed runtime tree."""
    found, stack = {}, list(direct)
    while stack:
        name = _norm(stack.pop())
        if name in found:
            continue
        try:
            dist = im.distribution(name)
        except im.PackageNotFoundError:
            continue
        found[name] = dist
        for req in dist.requires or []:
            # Skip optional extras (they aren't bundled unless separately required).
            if "extra ==" in req:
                continue
            dep = _dep_name(req)
            if dep and _norm(dep) not in found:
                stack.append(dep)
    return found


def license_name(dist) -> str:
    md = dist.metadata
    # Drop the bare "OSI Approved" parent category — it names no actual license.
    classifiers = [name for name in
                   (c.split("::")[-1].strip()
                    for c in (md.get_all("Classifier") or []) if c.startswith("License ::"))
                   if name and name != "OSI Approved"]
    if classifiers:
        return ", ".join(sorted(set(classifiers)))
    # PEP 639 SPDX expression (newer packages, e.g. numpy/click) or License field
    # (e.g. zeroconf, whose only classifier is the generic "OSI Approved").
    expr = (md.get("License-Expression") or "").strip()
    if expr:
        return expr
    lic = (md.get("License") or "").strip()
    return lic.splitlines()[0][:60] if lic else "see project"


def project_url(dist) -> str:
    md = dist.metadata
    home = (md.get("Home-page") or "").strip()
    if home and home.upper() != "UNKNOWN":
        return home
    by_label = {}
    for entry in md.get_all("Project-URL") or []:
        label, _, url = entry.partition(",")
        by_label[label.strip().lower()] = url.strip()
    for key in ("homepage", "source", "repository", "source code"):
        if key in by_label:
            return by_label[key]
    return next(iter(by_label.values()), "")


def license_text(dist) -> str | None:
    for f in dist.files or []:
        base = PurePosixPath(str(f)).name.lower()
        if base.startswith(("license", "copying", "notice")) and not base.endswith((".py", ".pyc")):
            try:
                return Path(dist.locate_file(f)).read_text(encoding="utf-8", errors="replace").strip()
            except Exception:
                continue
    return None


def main() -> None:
    root = Path(__file__).resolve().parent.parent
    dists = closure(DIRECT)
    rows = sorted(((d.metadata["Name"], d.version, license_name(d), project_url(d), d)
                   for d in dists.values()), key=lambda r: r[0].lower())

    out = []
    out.append("# Third-Party Licenses\n")
    out.append(f"_Generated by `packaging/gen_third_party_licenses.py` on {date.today().isoformat()}._\n")
    out.append("Setpoint and its Setpoint firmware are proprietary (see `LICENSE`). "
               "They are built on the open-source components below, each under its own license. "
               "This file ships with the product to satisfy those licenses' attribution terms.\n")

    out.append(LGPL_NOTICE)

    out.append("\n## Hub — Python packages (bundled in the executable)\n")
    out.append("| Package | Version | License | Project |")
    out.append("|---|---|---|---|")
    for name, ver, lic, url, _ in rows:
        link = f"[link]({url})" if url else "—"
        out.append(f"| {name} | {ver} | {lic} | {link} |")

    out.append("\n## Probe firmware — Arduino libraries\n")
    out.append("| Library | Author | License | Source |")
    out.append("|---|---|---|---|")
    for name, author, lic, url in FIRMWARE:
        out.append(f"| {name} | {author} | {lic} | [link]({url}) |")

    out.append("\n---\n\n## Full license texts (Python packages)\n")
    for name, ver, lic, url, dist in rows:
        out.append(f"\n### {name} {ver} — {lic}\n")
        text = license_text(dist)
        if text:
            out.append("```\n" + text + "\n```")
        else:
            out.append(f"License text not bundled with the package; see {url or 'the project page'}.")

    (root / "THIRD-PARTY-LICENSES.md").write_text("\n".join(out) + "\n", encoding="utf-8")
    print(f"Wrote THIRD-PARTY-LICENSES.md — {len(rows)} Python packages, "
          f"{len(FIRMWARE)} firmware libraries.")


if __name__ == "__main__":
    main()
