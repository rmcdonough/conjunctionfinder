"""Tests for the .ics feed builder (app/ics.py) and the rolling-window helpers
in app/transits.py that back it.
"""

from __future__ import annotations

from datetime import date

import pytest

from app.ics import build_ics_feed, build_single_event_ics, single_event_ics_filename
from app.transits import add_months, default_ics_window, find_conjunctions_for_dates


def test_add_months_basic():
    assert add_months(date(2026, 1, 15), 1) == date(2026, 2, 15)
    assert add_months(date(2026, 1, 15), -1) == date(2025, 12, 15)
    assert add_months(date(2026, 1, 15), 6) == date(2026, 7, 15)
    assert add_months(date(2026, 1, 15), 12) == date(2027, 1, 15)


def test_add_months_clamps_short_months():
    # Jan 31 + 1 month -> Feb has no 31st, so it clamps to the 28th (2026 is
    # not a leap year) rather than raising or overflowing into March.
    assert add_months(date(2026, 1, 31), 1) == date(2026, 2, 28)
    assert add_months(date(2024, 1, 31), 1) == date(2024, 2, 29)  # leap year


def test_default_ics_window_is_one_back_six_ahead():
    today = date(2026, 9, 10)
    start, end = default_ics_window(today)
    assert start == date(2026, 8, 10)
    assert end == date(2027, 3, 10)


def test_default_ics_window_recomputes_from_current_date():
    """The window is not cached — two calls a "day" apart both start from
    "today", so a subscribed feed re-fetched later has visibly moved on.
    """
    start1, end1 = default_ics_window(date(2026, 1, 1))
    start2, end2 = default_ics_window(date(2026, 2, 1))
    assert start2 > start1
    assert end2 > end1


def test_find_conjunctions_for_dates_respects_exact_bounds(chart):
    start = date(2026, 8, 10)
    end = date(2027, 3, 10)
    events = find_conjunctions_for_dates(chart, start, end, ["moon", "sun"])
    assert events, "expected real events in a 7-month window"
    for e in events:
        # utc is an ISO string; just check it's lexically within the window —
        # good enough since both are ISO 8601 and UTC.
        assert e.utc[:10] >= start.isoformat()
        assert e.utc[:10] <= (end.isoformat())


def test_build_ics_feed_shape(chart):
    events = find_conjunctions_for_dates(
        chart, date(2026, 8, 10), date(2026, 9, 10), ["moon"]
    )
    assert events
    text = build_ics_feed(chart, events, "Test Subject: Conjunctions")

    assert text.startswith("BEGIN:VCALENDAR\r\n")
    assert text.rstrip("\r\n").endswith("END:VCALENDAR")
    assert "VERSION:2.0\r\n" in text
    assert "X-WR-CALNAME:Test Subject: Conjunctions\r\n" in text
    assert text.count("BEGIN:VEVENT") == len(events)
    assert text.count("END:VEVENT") == len(events)

    for event in events:
        assert f"UID:" in text
    # Every event's SUMMARY line is present verbatim.
    body_name = {"moon": "Moon", "sun": "Sun"}
    for event in events:
        expected_summary = f"SUMMARY:{event.natal_key} conjunct Natal {body_name[event.transiting_body]}"
        assert expected_summary in text


def test_build_ics_feed_escapes_special_characters(chart):
    events = find_conjunctions_for_dates(
        chart, date(2026, 8, 10), date(2026, 8, 20), ["moon"]
    )
    assert events
    # Natal keys never contain these characters today, but the escaper must
    # still be correct in case a future point label does.
    text = build_ics_feed(chart, events, "A, B; C\\D")
    assert "X-WR-CALNAME:A\\, B\\; C\\\\D\r\n" in text


def test_build_ics_feed_empty_events_is_still_valid_calendar(chart):
    text = build_ics_feed(chart, [], "Empty")
    assert text.startswith("BEGIN:VCALENDAR\r\n")
    assert text.rstrip("\r\n").endswith("END:VCALENDAR")
    assert "BEGIN:VEVENT" not in text


def test_build_single_event_ics_shape():
    text = build_single_event_ics("moon", "1st House", "25\u00b016\u203200\u2033 Leo", "2026-06-15T14:30:00+00:00")
    assert text.startswith("BEGIN:VCALENDAR\r\n")
    assert text.rstrip("\r\n").endswith("END:VCALENDAR")
    assert text.count("BEGIN:VEVENT") == 1
    assert text.count("END:VEVENT") == 1
    assert "SUMMARY:1st House conjunct Natal Moon\r\n" in text
    assert "DTSTART:20260615T143000Z\r\n" in text
    assert "DTEND:20260615T150000Z\r\n" in text
    # No X-WR-CALNAME/METHOD — those are only meaningful for the multi-event
    # subscription feed, not a one-off single-event download.
    assert "X-WR-CALNAME" not in text
    assert "METHOD:" not in text


def test_build_single_event_ics_matches_feed_builder_output(chart):
    """The single-event builder and the multi-event feed builder must agree
    on VEVENT shape for the same underlying event — they're meant to be
    interchangeable per-event, just packaged differently."""
    events = find_conjunctions_for_dates(
        chart, date(2026, 8, 10), date(2026, 8, 20), ["moon"]
    )
    assert events
    event = events[0]
    single = build_single_event_ics(
        event.transiting_body, event.natal_key, event.natal_label, event.utc
    )
    feed = build_ics_feed(chart, [event], "Test")
    for prefix in ("UID:", "DTSTART:", "DTEND:", "SUMMARY:", "DESCRIPTION:"):
        single_line = next(line for line in single.split("\r\n") if line.startswith(prefix))
        feed_line = next(line for line in feed.split("\r\n") if line.startswith(prefix))
        assert single_line == feed_line


def test_single_event_ics_filename():
    name = single_event_ics_filename("moon", "1st House", "2026-06-15T14:30:00+00:00")
    assert name == "1st-house-conjunct-natal-moon-2026-06-15.ics"
