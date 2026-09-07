"""Swiss Ephemeris helpers.

Thin wrappers around ``pyswisseph`` (``import swisseph as swe``) so the rest of
the app never has to think about Julian Days, flag bits or ephemeris paths.

API names used here were verified against pyswisseph 2.10.03:
``swe.julday``, ``swe.revjul``, ``swe.calc_ut``, ``swe.houses``,
``swe.mooncross_ut``, ``swe.solcross_ut``, ``swe.set_ephe_path``,
``swe.FLG_SPEED``, ``swe.FLG_SWIEPH``, ``swe.MEAN_NODE``, ``swe.CHIRON``.
"""

from __future__ import annotations

import os
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path

import swisseph as swe

# ── Ephemeris data files ───────────────────────────────────────────────────
# The Swiss Ephemeris .se1 files ship in backend/ephe/ (semo_18, sepl_18,
# seas_18 — Moon, planets, asteroids for 1800–2400 AD). Chiron in particular
# REQUIRES the seas_* asteroid file; the built-in Moshier fallback cannot
# compute it. Override the location with the EPHE_PATH env var if needed.
EPHE_PATH = os.environ.get(
    "EPHE_PATH", str((Path(__file__).resolve().parent.parent / "ephe"))
)

# This pyswisseph build keeps the Swiss Ephemeris global state (including the
# ephemeris search path) in THREAD-LOCAL storage — verified empirically: a path
# set on the main thread is invisible to a worker thread, where Chiron then
# fails outright and the Moon silently falls back to the lower-precision
# built-in Moshier model. FastAPI runs `def` endpoints in a threadpool, so
# every entry point must (re)set the path on its own thread. `swe.set_ephe_path`
# closes any open ephemeris files, so we do it once per thread rather than once
# per call.
_thread_state = threading.local()


def ensure_ephe_path() -> None:
    """Point Swiss Ephemeris at our .se1 files, once per calling thread."""
    if getattr(_thread_state, "ephe_path", None) != EPHE_PATH:
        swe.set_ephe_path(EPHE_PATH)
        _thread_state.ephe_path = EPHE_PATH


ensure_ephe_path()

# Always ask for speed as well as position: the longitude speed component is
# what tells us whether a planet is retrograde (negative = retrograde).
CALC_FLAGS = swe.FLG_SWIEPH | swe.FLG_SPEED

ZODIAC_SIGNS = [
    "Aries", "Taurus", "Gemini", "Cancer",
    "Leo", "Virgo", "Libra", "Scorpio",
    "Sagittarius", "Capricorn", "Aquarius", "Pisces",
]


class EphemerisError(RuntimeError):
    """Raised when the Swiss Ephemeris cannot compute a requested position."""


def lon_to_label(lon: float) -> str:
    """Format a decimal ecliptic longitude as e.g. ``25°16′00″ Leo``.

    Matches the reference prototype's ``lon_to_label`` exactly.
    """
    lon = lon % 360.0
    sign_idx = int(lon // 30)
    deg_in_sign = lon % 30
    d = int(deg_in_sign)
    m = int((deg_in_sign - d) * 60)
    s = int(round(((deg_in_sign - d) * 60 - m) * 60))
    if s == 60:  # rounding edge case
        s = 59
    return f"{d}°{m:02d}′{s:02d}″ {ZODIAC_SIGNS[sign_idx]}"


def sign_of(lon: float) -> str:
    return ZODIAC_SIGNS[int((lon % 360.0) // 30)]


def degree_in_sign(lon: float) -> float:
    return (lon % 360.0) % 30


def datetime_to_jd(dt_utc: datetime) -> float:
    """Convert an aware UTC datetime to a Julian Day number (UT)."""
    if dt_utc.tzinfo is None:
        raise ValueError("datetime_to_jd requires a timezone-aware datetime")
    dt_utc = dt_utc.astimezone(timezone.utc)
    hour = dt_utc.hour + dt_utc.minute / 60.0 + (
        dt_utc.second + dt_utc.microsecond / 1e6
    ) / 3600.0
    return swe.julday(dt_utc.year, dt_utc.month, dt_utc.day, hour, swe.GREG_CAL)


def jd_to_datetime(jd: float) -> datetime:
    """Convert a Julian Day number (UT) to an aware UTC datetime."""
    year, month, day, frac_h = swe.revjul(jd, swe.GREG_CAL)
    total_seconds = round(frac_h * 3600.0)
    hour, rem = divmod(total_seconds, 3600)
    minute, second = divmod(rem, 60)
    # Rounding can push us to 24:00:00 — represent that as the next midnight.
    if hour == 24:
        base = datetime(year, month, day, 0, 0, 0, tzinfo=timezone.utc)
        return base + timedelta(days=1)
    return datetime(year, month, day, hour, minute, second, tzinfo=timezone.utc)


def body_longitude(jd_ut: float, body: int) -> tuple[float, float]:
    """Return ``(longitude, longitude_speed)`` for ``body`` at ``jd_ut``."""
    ensure_ephe_path()
    try:
        pos, _flags = swe.calc_ut(jd_ut, body, CALC_FLAGS)
    except swe.Error as exc:  # pragma: no cover - depends on ephe files
        raise EphemerisError(str(exc)) from exc
    # pos == (lon, lat, dist, lon_speed, lat_speed, dist_speed)
    return pos[0] % 360.0, pos[3]


def house_cusps(jd_ut: float, lat: float, lon: float) -> list[float]:
    """Placidus house cusps for houses 1..12, in order.

    Verified empirically with pyswisseph 2.10.03: ``swe.houses`` returns
    ``(cusps, ascmc)`` where ``cusps`` is a **12-tuple indexed from 0**, i.e.
    ``cusps[0]`` is the 1st-house cusp (== ``ascmc[0]``, the Ascendant) and
    ``cusps[9]`` is the 10th-house cusp (== ``ascmc[1]``, the MC). This differs
    from the C API, where ``cusps`` is a 13-element array whose element 0 is
    unused and houses live in ``cusps[1..12]``. We normalise to a plain
    list of 12 in house order here so callers never deal with the offset.
    """
    ensure_ephe_path()
    try:
        cusps, _ascmc = swe.houses(jd_ut, lat, lon, b"P")
    except swe.Error as exc:  # pragma: no cover
        raise EphemerisError(str(exc)) from exc
    if len(cusps) == 13:  # defensive: some builds mirror the C layout
        cusps = cusps[1:]
    return [c % 360.0 for c in cusps[:12]]


def moon_crossing(target_lon: float, jd_from: float) -> float:
    """Next Julian Day (UT) at/after ``jd_from`` when the Moon hits ``target_lon``."""
    ensure_ephe_path()
    try:
        return swe.mooncross_ut(target_lon % 360.0, jd_from, swe.FLG_SWIEPH)
    except swe.Error as exc:
        raise EphemerisError(str(exc)) from exc


def sun_crossing(target_lon: float, jd_from: float) -> float:
    """Next Julian Day (UT) at/after ``jd_from`` when the Sun hits ``target_lon``."""
    ensure_ephe_path()
    try:
        return swe.solcross_ut(target_lon % 360.0, jd_from, swe.FLG_SWIEPH)
    except swe.Error as exc:
        raise EphemerisError(str(exc)) from exc
