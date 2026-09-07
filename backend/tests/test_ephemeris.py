"""Unit tests for the Swiss Ephemeris wrappers.

Also pins the pyswisseph API shape we rely on, so an upgrade that moves the
goalposts (e.g. changes the ``swe.houses`` cusp indexing) fails loudly here
rather than silently producing a wrong chart.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
import swisseph as swe

from app.ephemeris import (
    ZODIAC_SIGNS,
    body_longitude,
    datetime_to_jd,
    degree_in_sign,
    house_cusps,
    jd_to_datetime,
    lon_to_label,
    moon_crossing,
    sign_of,
    sun_crossing,
)


def test_pyswisseph_exposes_the_api_we_use():
    for name in (
        "julday", "revjul", "calc_ut", "houses",
        "mooncross_ut", "solcross_ut", "set_ephe_path",
    ):
        assert callable(getattr(swe, name)), name
    for const in ("SUN", "MOON", "CHIRON", "MEAN_NODE", "FLG_SPEED", "FLG_SWIEPH"):
        assert isinstance(getattr(swe, const), int), const


def test_calc_ut_returns_six_values_plus_flags():
    jd = swe.julday(2000, 1, 1, 12.0, swe.GREG_CAL)
    pos, retflags = swe.calc_ut(jd, swe.SUN, swe.FLG_SWIEPH | swe.FLG_SPEED)
    assert len(pos) == 6
    assert isinstance(retflags, int)
    # Longitude speed is element 3 — that is what our retrograde flag reads.
    assert pos[3] == pytest.approx(1.019, abs=0.01)  # Sun ~1°/day


def test_houses_cusp_indexing_is_zero_based_twelve_tuple():
    """pyswisseph returns 12 cusps indexed from 0, not the C API's 13.

    ``cusps[0]`` must be the Ascendant (1st house) and ``cusps[9]`` the MC
    (10th house) — this is what ``house_cusps`` assumes.
    """
    jd = swe.julday(1971, 3, 15, 9.5, swe.GREG_CAL)
    cusps, ascmc = swe.houses(jd, 43.6532, -79.3832, b"P")
    assert len(cusps) == 12
    assert len(ascmc) == 8
    assert cusps[0] == pytest.approx(ascmc[0])  # 1st cusp == ASC
    assert cusps[9] == pytest.approx(ascmc[1])  # 10th cusp == MC

    ours = house_cusps(jd, 43.6532, -79.3832)
    assert len(ours) == 12
    assert ours[0] == pytest.approx(ascmc[0] % 360.0)
    assert ours[9] == pytest.approx(ascmc[1] % 360.0)
    assert all(0.0 <= c < 360.0 for c in ours)


def test_lon_to_label_matches_reference_prototype_format():
    # 25°16′00″ Leo == 120 + 25 + 16/60 (the reference chart's natal Moon).
    lon = 120 + 25 + 16 / 60.0
    assert lon_to_label(lon) == "25°16′00″ Leo"
    assert lon_to_label(0.0) == "0°00′00″ Aries"
    # Seconds are clamped at 59 rather than rolling over to 60.
    assert lon_to_label(359.9999) == "29°59′59″ Pisces"
    assert lon_to_label(360.0 + 15.5) == "15°30′00″ Aries"  # wraps


@pytest.mark.parametrize(
    "lon,expected",
    [
        (0.0, "Aries"),
        (29.99, "Aries"),
        (30.0, "Taurus"),
        (150.0, "Virgo"),
        (330.0, "Pisces"),
        (359.99, "Pisces"),
    ],
)
def test_sign_boundaries(lon, expected):
    assert sign_of(lon) == expected
    assert 0.0 <= degree_in_sign(lon) < 30.0
    assert ZODIAC_SIGNS.index(expected) * 30 <= lon < (ZODIAC_SIGNS.index(expected) + 1) * 30


def test_jd_roundtrip():
    dt = datetime(1971, 3, 15, 9, 30, 0, tzinfo=timezone.utc)
    jd = datetime_to_jd(dt)
    back = jd_to_datetime(jd)
    assert abs((back - dt).total_seconds()) < 1.0


def test_datetime_to_jd_requires_awareness():
    with pytest.raises(ValueError):
        datetime_to_jd(datetime(2000, 1, 1, 0, 0, 0))


def test_crossings_land_on_target():
    jd = swe.julday(2026, 6, 1, 0.0, swe.GREG_CAL)
    target = 145.0

    jd_moon = moon_crossing(target, jd)
    assert jd_moon > jd
    assert body_longitude(jd_moon, swe.MOON)[0] == pytest.approx(target, abs=1e-5)

    jd_sun = sun_crossing(target, jd)
    assert jd_sun > jd
    assert body_longitude(jd_sun, swe.SUN)[0] == pytest.approx(target, abs=1e-5)


def test_chiron_is_computable():
    """Chiron needs the seas_*.se1 asteroid file; assert it is actually there."""
    jd = swe.julday(2000, 1, 1, 0.0, swe.GREG_CAL)
    lon, _speed = body_longitude(jd, swe.CHIRON)
    assert 0.0 <= lon < 360.0


def test_ephemeris_path_is_set_per_thread():
    """Regression: this pyswisseph build stores the ephe path thread-locally.

    FastAPI runs sync endpoints in a threadpool, so if the path were only set at
    import time (on the main thread) Chiron would raise there and other bodies
    would silently drop to the low-precision Moshier fallback.
    """
    import threading

    jd = swe.julday(2000, 1, 1, 0.0, swe.GREG_CAL)
    expected = body_longitude(jd, swe.CHIRON)[0]
    result: dict[str, object] = {}

    def worker() -> None:
        try:
            result["lon"] = body_longitude(jd, swe.CHIRON)[0]
        except Exception as exc:  # pragma: no cover - only on regression
            result["error"] = exc

    t = threading.Thread(target=worker)
    t.start()
    t.join()

    assert "error" not in result, result["error"]
    assert result["lon"] == pytest.approx(expected)
