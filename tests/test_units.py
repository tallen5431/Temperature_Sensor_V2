"""Temperature conversion (core.units) — one home for arithmetic that used to be
written out in seven modules.

The Devices edit form and the dashboard both go through here now, so the two
distinctions callers rely on need pinning: absolute vs delta, and who rounds.
"""
import pathlib
import re

import pytest

from core.units import (c_to_f, delta_from_unit, delta_to_unit, f_to_c,
                        from_unit, to_unit, unit_symbol)

REPO = pathlib.Path(__file__).resolve().parent.parent


def test_absolute_conversion_round_trips():
    for c in (-40.0, -18.0, 0.0, 4.0, 21.5, 100.0):
        assert f_to_c(c_to_f(c)) == pytest.approx(c)
        assert from_unit(to_unit(c, "fahrenheit"), "fahrenheit") == pytest.approx(c)
        assert from_unit(to_unit(c, "kelvin"), "kelvin") == pytest.approx(c)
    assert c_to_f(-40.0) == -40.0            # the one place the scales meet
    assert to_unit(0.0, "kelvin") == 273.15


def test_a_delta_scales_but_never_shifts():
    """The distinction that makes this more than one function: -0.5 C of
    calibration correction is -0.9 F, not 31.1 F, and a Kelvin delta is a
    Celsius delta unchanged."""
    assert delta_to_unit(-0.5, "fahrenheit") == pytest.approx(-0.9)
    assert to_unit(-0.5, "fahrenheit") == pytest.approx(31.1)
    assert delta_to_unit(-0.5, "kelvin") == -0.5
    assert delta_from_unit(delta_to_unit(2.0, "fahrenheit"), "fahrenheit") \
        == pytest.approx(2.0)


def test_rounding_belongs_to_the_caller():
    # Unrounded by default (the dashboard keeps precision until format time)...
    assert to_unit(2.0, "fahrenheit") == pytest.approx(35.6)
    assert from_unit(35.6, "fahrenheit") != 2.0          # float noise survives
    # ...and rounded where a form field asks for it (what devices_panel passes).
    assert from_unit(35.6, "fahrenheit", ndigits=2) == 2.0


def test_none_and_unknown_units_degrade_to_celsius():
    for fn in (to_unit, from_unit, delta_to_unit, delta_from_unit):
        assert fn(None, "fahrenheit") is None
    # An absent or garbled unit preference reads as Celsius, which is what the
    # hub actually stores — degrade to the truth rather than to a guess.
    assert unit_symbol(None) == "°C"
    assert unit_symbol("nonsense") == "°C"
    assert to_unit(4.0, None) == 4.0
    assert unit_symbol("fahrenheit") == "°F" and unit_symbol("kelvin") == "K"


def test_the_formula_is_not_written_out_anywhere_else():
    """It was, in seven modules. Seven correct copies are seven places to check
    when something about temperature changes, and nothing keeps them agreeing
    except everyone remembering."""
    formula = re.compile(r"9\.0\s*/\s*5\.0|9\s*/\s*5\b|273\.15")
    offenders = []
    for path in REPO.rglob("*.py"):
        rel = path.relative_to(REPO).as_posix()
        if rel.startswith(("tests/", ".git/")) or "core/units.py" in rel:
            continue
        if formula.search(path.read_text(encoding="utf-8", errors="ignore")):
            offenders.append(rel)
    assert not offenders, f"convert via core.units instead: {offenders}"
