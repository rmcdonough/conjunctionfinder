"""Conjunction search tests."""

from __future__ import annotations

from collections import Counter
from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from app.transits import (
    STEP_DAYS,
    VERIFY_TOLERANCE_DEG,
    angular_separation,
    find_conjunctions,
    month_window_jd,
)


@pytest.fixture(scope="module")
def june_events(chart):
    return find_conjunctions(chart, 2026, 6, 2026, 6, ["moon", "sun"])


def test_angular_separation_wraps():
    assert angular_separation(1.0, 359.0) == pytest.approx(2.0)
    assert angular_separation(359.0, 1.0) == pytest.approx(2.0)
    assert angular_separation(10.0, 190.0) == pytest.approx(180.0)
    assert angular_separation(45.0, 45.0) == pytest.approx(0.0)


def test_month_window_covers_whole_months():
    jd_start, jd_end = month_window_jd(2026, 6, 2026, 6)
    assert jd_end - jd_start == pytest.approx(30.0)  # June has 30 days
    jd_start, jd_end = month_window_jd(2026, 1, 2026, 12)
    assert jd_end - jd_start == pytest.approx(365.0)  # 2026 is not a leap year


def test_every_event_is_verified_on_target(june_events):
    assert june_events, "June 2026 must yield Moon conjunctions"
    for e in june_events:
        sep = angular_separation(e.transiting_longitude, e.natal_longitude)
        assert sep <= VERIFY_TOLERANCE_DEG, (e.natal_key, e.utc, sep)
        # In practice the solver is far better than the tolerance.
        assert sep < 1e-5


def test_events_are_sorted_chronologically(june_events):
    jds = [e.julian_day for e in june_events]
    assert jds == sorted(jds)
    utcs = [e.utc for e in june_events]
    assert utcs == sorted(utcs)


def test_events_fall_inside_the_requested_window(june_events):
    for e in june_events:
        dt = datetime.fromisoformat(e.utc)
        assert dt.year == 2026
        assert dt.month == 6 or (dt.month == 7 and dt.day == 1 and dt.hour == 0)


def test_local_timestamps_use_the_birth_timezone(chart, june_events):
    tz = ZoneInfo(chart.timezone)
    for e in june_events:
        utc = datetime.fromisoformat(e.utc)
        local = datetime.fromisoformat(e.local)
        assert local == utc.astimezone(tz)
        # June in Toronto is EDT (-4).
        assert local.utcoffset().total_seconds() == -4 * 3600


def test_moon_hits_every_natal_point_each_month(chart, june_events):
    """The Moon laps the zodiac in ~27.3 days, so a 30-day month must hit all."""
    hit = {e.natal_key for e in june_events if e.transiting_body == "moon"}
    assert hit == {p.key for p in chart.points}


def test_sun_hits_each_natal_point_exactly_once_per_year(chart):
    events = find_conjunctions(chart, 2026, 1, 2026, 12, ["sun"])
    counts = Counter(e.natal_key for e in events)
    assert set(counts) == {p.key for p in chart.points}
    assert set(counts.values()) == {1}, counts


def test_body_selection_is_honoured(chart):
    moon_only = find_conjunctions(chart, 2026, 6, 2026, 6, ["moon"])
    sun_only = find_conjunctions(chart, 2026, 6, 2026, 6, ["sun"])
    both = find_conjunctions(chart, 2026, 6, 2026, 6, ["moon", "sun"])
    assert {e.transiting_body for e in moon_only} == {"moon"}
    assert {e.transiting_body for e in sun_only} == {"sun"}
    assert len(both) == len(moon_only) + len(sun_only)


def test_no_duplicate_events(june_events):
    seen = {(e.transiting_body, e.natal_key, round(e.julian_day, 6))
            for e in june_events}
    assert len(seen) == len(june_events)


def test_step_sizes_cannot_skip_a_crossing():
    """The forward hop must be shorter than the body's return period.

    Moon returns to a longitude every ~27.32 days, Sun every ~365.24 — stepping
    less than that guarantees the next crossing is still ahead of the search
    cursor, so nothing is skipped.
    """
    assert STEP_DAYS["moon"] < 27.32
    assert STEP_DAYS["sun"] < 365.24
    # ...and long enough to clear the crossing just found, so we never re-find it.
    assert STEP_DAYS["moon"] > 1.0
    assert STEP_DAYS["sun"] > 10.0
