"""End-to-end API tests through FastAPI's TestClient.

These exercise the same code paths a browser (or curl) hits, but with explicit
lat/lon so no geocoding network call is made.
"""

from __future__ import annotations

from datetime import datetime

import pytest
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)

BIRTH = {
    "birth_date": "1971-03-15",
    "birth_time": "04:30",
    "birth_place": "Toronto, Canada",
    "latitude": 43.6532,
    "longitude": -79.3832,
    "name": "Test Subject",
}


def test_health():
    r = client.get("/api/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_natal_chart_endpoint():
    r = client.post("/api/natal-chart", json=BIRTH)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["timezone"] == "America/Toronto"
    assert body["latitude"] == pytest.approx(43.6532)
    assert len(body["points"]) == 25
    keys = [p["key"] for p in body["points"]]
    assert "Sun" in keys and "Chiron" in keys and "Dragon's Tail" in keys
    assert "12th House" in keys
    for p in body["points"]:
        assert 0.0 <= p["longitude"] < 360.0
        assert isinstance(p["retrograde"], bool)
        assert p["label"]


def test_conjunctions_endpoint_returns_chart_and_events():
    r = client.post(
        "/api/conjunctions",
        json={**BIRTH, "start_year": 2026, "start_month": 6,
              "end_year": 2026, "end_month": 6, "bodies": ["moon", "sun"]},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["range_start"] == "2026-06-01"
    assert body["range_end"] == "2026-06-30"
    assert body["bodies"] == ["moon", "sun"]
    assert len(body["natal_chart"]["points"]) == 25
    events = body["events"]
    assert body["event_count"] == len(events)
    assert events, "expected real conjunction events"

    natal_by_key = {p["key"]: p for p in body["natal_chart"]["points"]}
    prev = None
    for e in events:
        assert e["transiting_body"] in {"moon", "sun"}
        assert e["natal_key"] in natal_by_key
        assert e["natal_longitude"] == pytest.approx(
            natal_by_key[e["natal_key"]]["longitude"]
        )
        # Verified transiting longitude really is on the natal degree.
        diff = abs(e["transiting_longitude"] - e["natal_longitude"]) % 360.0
        assert min(diff, 360.0 - diff) < 1e-5
        # Timestamps parse and stay sorted.
        utc = datetime.fromisoformat(e["utc"])
        datetime.fromisoformat(e["local"])
        if prev is not None:
            assert utc >= prev
        prev = utc


def test_defaults_to_both_bodies_when_omitted():
    r = client.post(
        "/api/conjunctions",
        json={**BIRTH, "start_year": 2026, "start_month": 6,
              "end_year": 2026, "end_month": 6},
    )
    assert r.status_code == 200, r.text
    assert r.json()["bodies"] == ["moon", "sun"]


def test_range_longer_than_twelve_months_is_rejected():
    r = client.post(
        "/api/conjunctions",
        json={**BIRTH, "start_year": 2026, "start_month": 1,
              "end_year": 2027, "end_month": 1},
    )
    assert r.status_code == 422
    assert "12" in r.text


def test_exactly_twelve_months_is_accepted():
    r = client.post(
        "/api/conjunctions",
        json={**BIRTH, "start_year": 2026, "start_month": 1,
              "end_year": 2026, "end_month": 12, "bodies": ["sun"]},
    )
    assert r.status_code == 200, r.text
    assert r.json()["event_count"] == 25  # one solar conjunction per natal point


def test_end_before_start_is_rejected():
    r = client.post(
        "/api/conjunctions",
        json={**BIRTH, "start_year": 2026, "start_month": 6,
              "end_year": 2026, "end_month": 5},
    )
    assert r.status_code == 422
    assert "before" in r.text


def test_empty_body_selection_is_rejected():
    r = client.post(
        "/api/conjunctions",
        json={**BIRTH, "start_year": 2026, "start_month": 6,
              "end_year": 2026, "end_month": 6, "bodies": []},
    )
    assert r.status_code == 422
    assert "at least one" in r.text


def test_missing_place_and_coords_is_rejected():
    r = client.post(
        "/api/natal-chart",
        json={"birth_date": "1971-03-15", "birth_time": "04:30"},
    )
    assert r.status_code == 422
    assert "birth_place" in r.text


def test_bad_date_is_rejected():
    r = client.post(
        "/api/natal-chart",
        json={**BIRTH, "birth_date": "1971-02-30"},
    )
    assert r.status_code == 422


def test_lat_lon_out_of_range_is_rejected():
    r = client.post("/api/natal-chart", json={**BIRTH, "latitude": 100.0})
    assert r.status_code == 422


def test_unresolvable_place_name_returns_400():
    r = client.post(
        "/api/natal-chart",
        json={
            "birth_date": "1971-03-15",
            "birth_time": "04:30",
            "birth_place": "Xyzzy Nowhereville, Atlantis",
        },
    )
    # 400 when the geocoder answers "no match", or when it is unreachable —
    # either way it is the caller's input we cannot act on.
    assert r.status_code == 400
    assert "Could not find" in r.text or "unavailable" in r.text


@pytest.mark.network
def test_geocoding_a_known_city():
    """Real Nominatim lookup — run with RUN_NETWORK_TESTS=1."""
    r = client.post(
        "/api/natal-chart",
        json={
            "birth_date": "1971-03-15",
            "birth_time": "04:30",
            "birth_place": "Toronto, Ontario, Canada",
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["latitude"] == pytest.approx(43.65, abs=0.2)
    assert body["longitude"] == pytest.approx(-79.38, abs=0.2)
    assert body["timezone"] == "America/Toronto"
    assert "Toronto" in body["resolved_place"]


# ── /api/conjunctions.ics ────────────────────────────────────────────────

ICS_PARAMS = {
    "birth_date": "1971-03-15",
    "birth_time": "04:30",
    "latitude": 43.6532,
    "longitude": -79.3832,
}


def test_ics_feed_returns_valid_calendar():
    r = client.get("/api/conjunctions.ics", params=ICS_PARAMS)
    assert r.status_code == 200, r.text
    assert r.headers["content-type"].startswith("text/calendar")
    assert 'filename="conjunctions.ics"' in r.headers["content-disposition"]
    text = r.text
    assert text.startswith("BEGIN:VCALENDAR\r\n")
    assert text.rstrip("\r\n").endswith("END:VCALENDAR")
    assert "BEGIN:VEVENT" in text  # Moon alone guarantees at least one hit


def test_ics_feed_defaults_to_both_bodies():
    r = client.get("/api/conjunctions.ics", params=ICS_PARAMS)
    assert r.status_code == 200, r.text
    assert "conjunct Natal Moon" in r.text
    assert "conjunct Natal Sun" in r.text


def test_ics_feed_honours_body_selection():
    r = client.get(
        "/api/conjunctions.ics",
        params={**ICS_PARAMS, "bodies": ["sun"]},
    )
    assert r.status_code == 200, r.text
    assert "conjunct Natal Sun" in r.text
    assert "conjunct Natal Moon" not in r.text


def test_ics_feed_uses_display_name_in_calendar_name():
    r = client.get("/api/conjunctions.ics", params={**ICS_PARAMS, "name": "Rich"})
    assert r.status_code == 200, r.text
    assert "X-WR-CALNAME:Rich: Conjunctions" in r.text


def test_ics_feed_missing_birth_date_is_422():
    params = {k: v for k, v in ICS_PARAMS.items() if k != "birth_date"}
    r = client.get("/api/conjunctions.ics", params=params)
    assert r.status_code == 422


def test_ics_feed_missing_place_and_coords_is_422():
    r = client.get(
        "/api/conjunctions.ics",
        params={"birth_date": "1971-03-15", "birth_time": "04:30"},
    )
    assert r.status_code == 422


def test_ics_feed_unresolvable_place_is_400():
    r = client.get(
        "/api/conjunctions.ics",
        params={
            "birth_date": "1971-03-15",
            "birth_time": "04:30",
            "birth_place": "Xyzzy Nowhereville, Atlantis",
        },
    )
    assert r.status_code == 400


# ── /api/conjunction-event.ics ──────────────────────────────────────────────

EVENT_ICS_PARAMS = {
    "transiting_body": "moon",
    "natal_key": "1st House",
    "natal_label": "25\u00b016\u203200\u2033 Leo",
    "utc": "2026-06-15T14:30:00+00:00",
}


def test_conjunction_event_ics_returns_valid_single_event_calendar():
    r = client.get("/api/conjunction-event.ics", params=EVENT_ICS_PARAMS)
    assert r.status_code == 200, r.text
    assert r.headers["content-type"].startswith("text/calendar")
    assert "attachment" in r.headers["content-disposition"]
    assert "1st-house-conjunct-natal-moon-2026-06-15.ics" in r.headers["content-disposition"]
    text = r.text
    assert text.startswith("BEGIN:VCALENDAR\r\n")
    assert text.rstrip("\r\n").endswith("END:VCALENDAR")
    assert text.count("BEGIN:VEVENT") == 1
    assert text.count("END:VEVENT") == 1
    assert "SUMMARY:1st House conjunct Natal Moon\r\n" in text
    assert "DTSTART:20260615T143000Z\r\n" in text
    assert "DTEND:20260615T150000Z\r\n" in text  # 30-minute visible span


def test_conjunction_event_ics_honours_sun():
    r = client.get(
        "/api/conjunction-event.ics",
        params={**EVENT_ICS_PARAMS, "transiting_body": "sun"},
    )
    assert r.status_code == 200, r.text
    assert "SUMMARY:1st House conjunct Natal Sun\r\n" in r.text


def test_conjunction_event_ics_escapes_special_characters():
    r = client.get(
        "/api/conjunction-event.ics",
        params={**EVENT_ICS_PARAMS, "natal_key": "A, B; C"},
    )
    assert r.status_code == 200, r.text
    assert "SUMMARY:A\\, B\\; C conjunct Natal Moon\r\n" in r.text


def test_conjunction_event_ics_rejects_bad_timestamp():
    r = client.get(
        "/api/conjunction-event.ics",
        params={**EVENT_ICS_PARAMS, "utc": "not-a-timestamp"},
    )
    assert r.status_code == 422


def test_conjunction_event_ics_rejects_bad_body():
    r = client.get(
        "/api/conjunction-event.ics",
        params={**EVENT_ICS_PARAMS, "transiting_body": "mars"},
    )
    assert r.status_code == 422


def test_conjunction_event_ics_requires_all_params():
    params = {k: v for k, v in EVENT_ICS_PARAMS.items() if k != "natal_key"}
    r = client.get("/api/conjunction-event.ics", params=params)
    assert r.status_code == 422
