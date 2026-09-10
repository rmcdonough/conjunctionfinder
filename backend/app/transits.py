"""Conjunction search: transiting Moon/Sun crossing natal longitudes.

Mirrors the reference prototype (``reference/moon_transits.py``): for every
natal point, repeatedly ask the Swiss Ephemeris for the next moment the
transiting body crosses that exact ecliptic longitude, then hop forward past
the crossing and ask again, until we run past the end of the window.
"""

from __future__ import annotations

import calendar
from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo

import swisseph as swe

from .ephemeris import (
    EphemerisError,
    body_longitude,
    jd_to_datetime,
    lon_to_label,
    moon_crossing,
    sun_crossing,
)
from .schemas import ConjunctionEvent, NatalChart, TransitingBody

# How far to jump past a found crossing before searching for the next one.
#
# Moon: it returns to a given ecliptic longitude every tropical month, ~27.32
# days, so 25 days clears the crossing we just found without any chance of
# skipping over the following one. (Same value as the reference script.)
#
# Sun: it laps the zodiac in ~365.24 days, so each natal point gets exactly one
# solar conjunction per year. 340 days is comfortably past the crossing we just
# found (no risk of re-finding it, even with the ~±2 day annual wobble in the
# Sun's apparent speed) and still ~25 days short of the next one, so nothing
# can be missed.
STEP_DAYS = {"moon": 25.0, "sun": 340.0}

CROSSING_FN = {"moon": moon_crossing, "sun": sun_crossing}

BODY_CONST = {"moon": swe.MOON, "sun": swe.SUN}

# A crossing is accepted only if recomputing the body's longitude at the
# returned instant lands within this many degrees of the natal target.
# In practice pyswisseph nails it to <1e-6°; 1 arcminute is a generous guard
# against a solver that returned without converging.
VERIFY_TOLERANCE_DEG = 1.0 / 60.0


def angular_separation(a: float, b: float) -> float:
    """Smallest absolute angle between two ecliptic longitudes, in degrees."""
    diff = abs((a - b) % 360.0)
    return min(diff, 360.0 - diff)


def month_window_jd(
    start_year: int, start_month: int, end_year: int, end_month: int
) -> tuple[float, float]:
    """Julian Day bounds ``[start, end)`` covering whole months, inclusive.

    The upper bound is midnight UT starting the day *after* the last day of
    ``end_month``, i.e. a clean exclusive bound — no ``23.9999`` fudge factor.
    """
    jd_start = swe.julday(start_year, start_month, 1, 0.0, swe.GREG_CAL)
    last_day = calendar.monthrange(end_year, end_month)[1]
    jd_end = swe.julday(end_year, end_month, last_day, 24.0, swe.GREG_CAL)
    return jd_start, jd_end


def date_range_jd(start_date: date, end_date: date) -> tuple[float, float]:
    """Julian Day bounds ``[start, end]`` covering two calendar dates.

    Unlike ``month_window_jd`` this is not padded to whole months — the
    caller's ``start_date``/``end_date`` are used exactly, with the end date
    treated as inclusive (bound runs to the following midnight UT).
    """
    jd_start = swe.julday(start_date.year, start_date.month, start_date.day, 0.0, swe.GREG_CAL)
    jd_end = swe.julday(end_date.year, end_date.month, end_date.day, 24.0, swe.GREG_CAL)
    return jd_start, jd_end


def add_months(d: date, months: int) -> date:
    """``d`` shifted by ``months`` (may be negative), clamped to a valid day.

    E.g. add_months(date(2026, 1, 31), 1) -> date(2026, 2, 28) rather than
    raising on "February 31st".
    """
    total = d.year * 12 + (d.month - 1) + months
    year, month0 = divmod(total, 12)
    month = month0 + 1
    day = min(d.day, calendar.monthrange(year, month)[1])
    return date(year, month, day)


def default_ics_window(today: date | None = None) -> tuple[date, date]:
    """The rolling window the public .ics feed covers: 1 month back, 6 ahead.

    Recomputed from the current date every time this is called (there is no
    caching here), so a calendar client that re-polls the same subscription
    URL days or weeks later gets a window that has slid forward with it —
    that is the entire point of a *subscription* feed versus a one-off
    download of a fixed range.
    """
    if today is None:
        today = datetime.now(timezone.utc).date()
    return add_months(today, -1), add_months(today, 6)


def _search_crossings(
    chart: NatalChart,
    jd_start: float,
    jd_end: float,
    bodies: list[TransitingBody],
) -> list[ConjunctionEvent]:
    """Shared search loop behind both ``find_conjunctions`` variants below."""
    local_tz = ZoneInfo(chart.timezone)

    events: list[ConjunctionEvent] = []

    for body in bodies:
        crossing_fn = CROSSING_FN[body]
        step = STEP_DAYS[body]
        body_const = BODY_CONST[body]

        for point in chart.points:
            target = point.longitude
            jd_search = jd_start

            while jd_search < jd_end:
                try:
                    jd_cross = crossing_fn(target, jd_search)
                except EphemerisError:
                    # No further crossing findable from here (mirrors the
                    # reference script swallowing the solver's RuntimeError).
                    break

                if jd_cross is None or jd_cross >= jd_end:
                    break

                # Guard against a solver that fails to advance, which would
                # otherwise spin forever on this natal point.
                if jd_cross < jd_search:
                    break

                # Verify: recompute the transiting body's longitude at the
                # exact instant returned and confirm it really is on target.
                transiting_lon, _speed = body_longitude(jd_cross, body_const)
                if angular_separation(transiting_lon, target) <= VERIFY_TOLERANCE_DEG:
                    dt_utc = jd_to_datetime(jd_cross)
                    events.append(
                        ConjunctionEvent(
                            utc=dt_utc.isoformat(),
                            local=dt_utc.astimezone(local_tz).isoformat(),
                            julian_day=jd_cross,
                            transiting_body=body,
                            natal_key=point.key,
                            natal_label=point.label,
                            natal_longitude=target,
                            transiting_longitude=transiting_lon,
                            transiting_label=lon_to_label(transiting_lon),
                        )
                    )

                jd_search = jd_cross + step

    events.sort(key=lambda e: (e.julian_day, e.transiting_body, e.natal_key))
    return events


def find_conjunctions(
    chart: NatalChart,
    start_year: int,
    start_month: int,
    end_year: int,
    end_month: int,
    bodies: list[TransitingBody],
) -> list[ConjunctionEvent]:
    """Every Moon/Sun conjunction with a natal point inside the month window.

    Returns events sorted chronologically.
    """
    jd_start, jd_end = month_window_jd(start_year, start_month, end_year, end_month)
    return _search_crossings(chart, jd_start, jd_end, bodies)


def find_conjunctions_for_dates(
    chart: NatalChart,
    start_date: date,
    end_date: date,
    bodies: list[TransitingBody],
) -> list[ConjunctionEvent]:
    """Every conjunction inside ``[start_date, end_date]`` (exact dates, not
    padded to whole calendar months). Used by the .ics subscription feed's
    rolling window (see ``default_ics_window``).
    """
    jd_start, jd_end = date_range_jd(start_date, end_date)
    return _search_crossings(chart, jd_start, jd_end, bodies)
