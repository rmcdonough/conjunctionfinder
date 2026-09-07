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
