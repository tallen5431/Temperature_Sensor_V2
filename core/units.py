"""Temperature conversion — the one place the arithmetic lives.

``(t_c * 9.0 / 5.0) + 32.0`` was written out in seven modules (ingest, bulk
ingest, storage, the CSV migration, alert formatting, the demo generator) and
``_unit_symbol`` existed twice, in two component files, with two different
quote styles. None of them were wrong, which is the problem: seven correct
copies are seven places to check when something about temperature changes, and
nothing makes them agree except everyone remembering.

Two distinctions the callers care about, and the reason this is more than one
function:

**Absolute vs delta.** A temperature and a temperature *difference* convert
differently. A delta scales but never shifts — ``-0.5 °C`` of calibration
correction is ``-0.9 °F``, not ``31.1 °F`` — and a Kelvin delta is a Celsius
delta unchanged.

**Rounding belongs to the caller.** Form fields round to 2 dp so an operator
sees ``35.6`` rather than ``35.60000000000001``; the dashboard rounds at format
time and wants full precision until then. Pass ``ndigits`` where you want it
rather than having a rounded and an unrounded copy of each function.
"""
from __future__ import annotations

from typing import Optional

FAHRENHEIT = "fahrenheit"
KELVIN = "kelvin"
CELSIUS = "celsius"

_KELVIN_OFFSET = 273.15


def c_to_f(c: float) -> float:
    """Celsius to Fahrenheit. Callers pass an already-validated float."""
    return (c * 9.0 / 5.0) + 32.0


def f_to_c(f: float) -> float:
    return (f - 32.0) * 5.0 / 9.0


def unit_symbol(unit: Optional[str]) -> str:
    """Display symbol for a unit name. Anything unrecognised reads as Celsius,
    which is what the hub stores, so a missing/garbled preference degrades to
    the truth rather than to a guess."""
    if unit == FAHRENHEIT:
        return "°F"
    if unit == KELVIN:
        return "K"
    return "°C"


def _round(value: float, ndigits: Optional[int]) -> float:
    return value if ndigits is None else round(value, ndigits)


def to_unit(temp_c, unit: Optional[str], ndigits: Optional[int] = None):
    """Absolute Celsius temperature -> ``unit``. ``None`` passes through."""
    if temp_c is None:
        return None
    t = float(temp_c)
    if unit == FAHRENHEIT:
        return _round(c_to_f(t), ndigits)
    if unit == KELVIN:
        return _round(t + _KELVIN_OFFSET, ndigits)
    return t


def from_unit(value, unit: Optional[str], ndigits: Optional[int] = None):
    """Absolute temperature entered in ``unit`` -> Celsius. ``None`` passes through."""
    if value is None:
        return None
    v = float(value)
    if unit == FAHRENHEIT:
        return _round(f_to_c(v), ndigits)
    if unit == KELVIN:
        return _round(v - _KELVIN_OFFSET, ndigits)
    return v


def delta_to_unit(delta_c, unit: Optional[str], ndigits: Optional[int] = None):
    """Celsius temperature DELTA -> ``unit``. Scales, never shifts."""
    if delta_c is None:
        return None
    d = float(delta_c)
    if unit == FAHRENHEIT:
        return _round(d * 9.0 / 5.0, ndigits)
    return d


def delta_from_unit(value, unit: Optional[str], ndigits: Optional[int] = None):
    """Temperature DELTA entered in ``unit`` -> Celsius."""
    if value is None:
        return None
    v = float(value)
    if unit == FAHRENHEIT:
        return _round(v * 5.0 / 9.0, ndigits)
    return v
