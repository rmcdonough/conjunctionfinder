"""Natal chart computation.

Birth date + time + place → the list of natal points (luminaries, planets,
Chiron, the lunar nodes and the 12 Placidus house cusps) that the conjunction
search runs against.
"""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

import swisseph as swe

from .ephemeris import (
    body_longitude,
    datetime_to_jd,
    degree_in_sign,
    house_cusps,
    lon_to_label,
    sign_of,
)
from .location import ResolvedLocation, resolve_location
from .schemas import BirthInfo, NatalChart, NatalPoint

# (key, swisseph constant, category). Order mirrors the classic chart listing.
BODIES: list[tuple[str, int, str]] = [
    ("Sun", swe.SUN, "luminary"),
    ("Moon", swe.MOON, "luminary"),
    ("Mercury", swe.MERCURY, "planet"),
    ("Venus", swe.VENUS, "planet"),
    ("Mars", swe.MARS, "planet"),
    ("Jupiter", swe.JUPITER, "planet"),
    ("Saturn", swe.SATURN, "planet"),
    ("Uranus", swe.URANUS, "planet"),
    ("Neptune", swe.NEPTUNE, "planet"),
    ("Pluto", swe.PLUTO, "planet"),
    ("Chiron", swe.CHIRON, "planet"),
]

HOUSE_NAMES = [
    "1st House", "2nd House", "3rd House", "4th House",
    "5th House", "6th House", "7th House", "8th House",
    "9th House", "10th House", "11th House", "12th House",
]


def _point(key: str, category: str, lon: float, retrograde: bool,
           speed: float | None) -> NatalPoint:
    return NatalPoint(
        key=key,
        category=category,
        longitude=lon % 360.0,
        sign=sign_of(lon),
        degree_in_sign=degree_in_sign(lon),
        label=lon_to_label(lon),
        retrograde=retrograde,
        speed=speed,
    )


def birth_datetimes(
    info: BirthInfo, tz_name: str
) -> tuple[datetime, datetime]:
    """Interpret the birth date/time as local wall clock in ``tz_name``.

    ``zoneinfo`` applies the historical DST / UTC-offset rules that were in
    force on the birth date, which a fixed offset would get wrong.
    """
    tz = ZoneInfo(tz_name)
    local = datetime.combine(info.birth_date, info.birth_time, tzinfo=tz)
    return local, local.astimezone(ZoneInfo("UTC"))


def compute_natal_chart(
    info: BirthInfo, location: ResolvedLocation | None = None
) -> NatalChart:
    """Compute the full natal chart for the given birth info."""
    if location is None:
        location = resolve_location(
            place=info.birth_place,
            latitude=info.latitude,
            longitude=info.longitude,
        )

    local_dt, utc_dt = birth_datetimes(info, location.timezone)
    jd_ut = datetime_to_jd(utc_dt)

    points: list[NatalPoint] = []

    for key, body, category in BODIES:
        lon, speed = body_longitude(jd_ut, body)
        # Retrograde is simply apparent backwards motion: negative longitude speed.
        points.append(_point(key, category, lon, retrograde=speed < 0, speed=speed))

    # Lunar nodes. The mean node's longitude speed is always negative (it
    # regresses ~19°/year), so deriving a retrograde flag from speed would mark
    # every chart's nodes retrograde — the reference chart's table prints no
    # (R) for the Dragon's Head/Tail, so we follow that convention and report
    # retrograde=False for nodes while still exposing the real speed.
    node_lon, node_speed = body_longitude(jd_ut, swe.MEAN_NODE)
    points.append(_point("Dragon's Head", "node", node_lon, False, node_speed))
    points.append(
        _point("Dragon's Tail", "node", node_lon + 180.0, False, node_speed)
    )

    # House cusps (Placidus). Retrograde is meaningless for a cusp.
    for name, cusp in zip(HOUSE_NAMES, house_cusps(jd_ut, location.latitude,
                                                   location.longitude)):
        points.append(_point(name, "house", cusp, False, None))

    return NatalChart(
        name=info.name,
        points=points,
        latitude=location.latitude,
        longitude=location.longitude,
        resolved_place=location.display_name,
        timezone=location.timezone,
        birth_datetime_local=local_dt.isoformat(),
        birth_datetime_utc=utc_dt.isoformat(),
        julian_day=jd_ut,
    )
