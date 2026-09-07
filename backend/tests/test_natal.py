"""Natal chart tests.

The reference prototype's hardcoded chart (`reference/moon_transits.py`) is not
reproducible from these tests — the birth data behind it was never recorded, so
there is nothing to reproduce it *from*. Instead we assert the structural and
astronomical invariants that any correct chart must satisfy, plus a couple of
independently checkable facts (Sun's sign on a known date, ASC == 1st cusp).
"""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

import pytest
import swisseph as swe

from app.ephemeris import house_cusps
from app.natal import BODIES, HOUSE_NAMES, compute_natal_chart
from app.schemas import BirthInfo

EXPECTED_KEYS = (
    [key for key, _const, _cat in BODIES]
    + ["Dragon's Head", "Dragon's Tail"]
    + HOUSE_NAMES
)


def test_chart_has_every_expected_point(chart):
    assert [p.key for p in chart.points] == EXPECTED_KEYS
    assert len(chart.points) == 25  # 11 bodies + 2 nodes + 12 cusps


def test_all_longitudes_in_range_and_labels_agree(chart):
    for p in chart.points:
        assert 0.0 <= p.longitude < 360.0, p.key
        assert 0.0 <= p.degree_in_sign < 30.0, p.key
        # The label must describe the same longitude it was derived from.
        assert p.label.endswith(p.sign), p.key
        d, rest = p.label.split("°", 1)
        m, rest = rest.split("′", 1)
        s, _sign = rest.split("″", 1)
        from_label = int(d) + int(m) / 60.0 + int(s) / 3600.0
        # Label seconds are rounded (and clamped at 59), so allow 2 arcseconds.
        assert from_label == pytest.approx(p.degree_in_sign, abs=2 / 3600.0), p.key


def test_categories_are_assigned(chart):
    by_key = {p.key: p for p in chart.points}
    assert by_key["Sun"].category == "luminary"
    assert by_key["Moon"].category == "luminary"
    assert by_key["Pluto"].category == "planet"
    assert by_key["Chiron"].category == "planet"
    assert by_key["Dragon's Head"].category == "node"
    assert by_key["7th House"].category == "house"


def test_nodes_are_exactly_opposite(chart):
    by_key = {p.key: p for p in chart.points}
    head = by_key["Dragon's Head"].longitude
    tail = by_key["Dragon's Tail"].longitude
    assert (tail - head) % 360.0 == pytest.approx(180.0, abs=1e-9)


def test_opposite_house_cusps_are_180_apart(chart):
    by_key = {p.key: p for p in chart.points}
    for i in range(1, 7):
        a = by_key[HOUSE_NAMES[i - 1]].longitude
        b = by_key[HOUSE_NAMES[i + 5]].longitude
        assert (b - a) % 360.0 == pytest.approx(180.0, abs=1e-6), HOUSE_NAMES[i - 1]


def test_first_house_cusp_is_the_ascendant(chart):
    _cusps, ascmc = swe.houses(chart.julian_day, chart.latitude, chart.longitude, b"P")
    by_key = {p.key: p for p in chart.points}
    assert by_key["1st House"].longitude == pytest.approx(ascmc[0] % 360.0)
    assert by_key["10th House"].longitude == pytest.approx(ascmc[1] % 360.0)


def test_house_cusps_have_no_speed_or_retrograde(chart):
    for name in HOUSE_NAMES:
        p = next(p for p in chart.points if p.key == name)
        assert p.speed is None
        assert p.retrograde is False


def test_retrograde_is_derived_from_speed(chart):
    for p in chart.points:
        if p.category in {"luminary", "planet"}:
            assert p.retrograde == (p.speed < 0), p.key
    # Sun and Moon are never retrograde in geocentric ecliptic longitude.
    by_key = {p.key: p for p in chart.points}
    assert by_key["Sun"].retrograde is False
    assert by_key["Moon"].retrograde is False


def test_birth_time_is_interpreted_as_local_wall_clock(chart):
    # 1971-03-15 is before Toronto's DST start, so the offset must be EST (-5).
    local = datetime.fromisoformat(chart.birth_datetime_local)
    utc = datetime.fromisoformat(chart.birth_datetime_utc)
    assert chart.timezone == "America/Toronto"
    assert local.hour == 4 and local.minute == 30
    assert local.utcoffset().total_seconds() == -5 * 3600
    assert utc.hour == 9 and utc.minute == 30
    assert local.astimezone(ZoneInfo("UTC")) == utc


def test_historical_dst_rules_are_respected():
    """A summer birth in the same place must come out at -4, not -5."""
    summer = compute_natal_chart(
        BirthInfo(
            birth_date="1971-07-15",
            birth_time="04:30",
            latitude=43.6532,
            longitude=-79.3832,
        )
    )
    local = datetime.fromisoformat(summer.birth_datetime_local)
    assert local.utcoffset().total_seconds() == -4 * 3600


def test_sun_sign_on_a_known_date():
    """15 March is always late Pisces — an independent sanity anchor."""
    by_key = {p.key: p for p in compute_natal_chart(
        BirthInfo(
            birth_date="1971-03-15",
            birth_time="12:00",
            latitude=43.6532,
            longitude=-79.3832,
        )
    ).points}
    assert by_key["Sun"].sign == "Pisces"
    assert by_key["Sun"].degree_in_sign > 20.0


def test_explicit_coords_skip_geocoding_and_resolve_timezone(chart):
    assert chart.latitude == pytest.approx(43.6532)
    assert chart.longitude == pytest.approx(-79.3832)
    assert chart.timezone == "America/Toronto"


def test_julian_day_matches_utc_instant(chart):
    utc = datetime.fromisoformat(chart.birth_datetime_utc)
    expected = swe.julday(
        utc.year, utc.month, utc.day, utc.hour + utc.minute / 60.0, swe.GREG_CAL
    )
    assert chart.julian_day == pytest.approx(expected, abs=1e-9)


def test_house_cusps_change_with_birth_time(chart):
    """Sanity-check the "exact time matters" claim the UI makes."""
    later = house_cusps(chart.julian_day + 1 / 24.0, chart.latitude, chart.longitude)
    first_now = next(p for p in chart.points if p.key == "1st House").longitude
    assert abs((later[0] - first_now) % 360.0) > 1.0
