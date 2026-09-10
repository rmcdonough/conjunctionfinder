"""FastAPI application.

The same ASGI app object runs two ways:
  * locally:  ``uvicorn app.main:app --reload --port 8000``
  * on Lambda: via the Mangum adapter exported as ``handler`` (see template.yaml)

Fully stateless — no auth, no database, nothing persisted between requests.
"""

from __future__ import annotations

import os
from typing import Annotated

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import PlainTextResponse
from mangum import Mangum

from .ephemeris import EphemerisError
from .ics import build_ics_feed
from .location import LocationError, resolve_location
from .natal import compute_natal_chart
from .schemas import (
    BirthInfo,
    ConjunctionsRequest,
    ConjunctionsResponse,
    NatalChart,
    TransitingBody,
)
from .transits import default_ics_window, find_conjunctions, find_conjunctions_for_dates

# Allowed CORS origins, comma-separated. Default covers the Vite dev server on
# both the hostname and loopback-IP spellings it may be reached by.
DEFAULT_ORIGINS = "http://localhost:5173,http://127.0.0.1:5173"
ALLOWED_ORIGINS = [
    origin.strip()
    for origin in os.environ.get("ALLOWED_ORIGINS", DEFAULT_ORIGINS).split(",")
    if origin.strip()
]

app = FastAPI(
    title="Astrology Conjunction Finder",
    version="1.0.0",
    description=(
        "Computes a natal chart and finds every transiting Moon/Sun conjunction "
        "with a natal point over a date range of up to 12 months."
    ),
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health")
def health() -> dict[str, object]:
    return {"status": "ok", "allowed_origins": ALLOWED_ORIGINS}


@app.post("/api/natal-chart", response_model=NatalChart)
def natal_chart(info: BirthInfo) -> NatalChart:
    """Resolve the birth place/timezone and compute the natal chart."""
    try:
        return compute_natal_chart(info)
    except LocationError as exc:
        # Unresolvable place name / timezone is the caller's problem to fix.
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except EphemerisError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/conjunctions", response_model=ConjunctionsResponse)
def conjunctions(request: ConjunctionsRequest) -> ConjunctionsResponse:
    """Compute the natal chart *and* the conjunction list in one round trip."""
    try:
        # Resolve the location once and reuse it, so the geocoder is hit at most
        # once per request and the chart's timezone is the one used for the
        # events' local timestamps.
        location = resolve_location(
            place=request.birth_place,
            latitude=request.latitude,
            longitude=request.longitude,
        )
        chart = compute_natal_chart(request, location=location)
        events = find_conjunctions(
            chart,
            start_year=request.start_year,
            start_month=request.start_month,
            end_year=request.end_year,
            end_month=request.end_month,
            bodies=request.bodies,
        )
    except LocationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except EphemerisError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return ConjunctionsResponse(
        natal_chart=chart,
        events=events,
        event_count=len(events),
        range_start=request.range_start_date.isoformat(),
        range_end=request.range_end_date.isoformat(),
        bodies=request.bodies,
    )


# Query-string equivalent of ConjunctionsRequest's birth fields, minus the
# search window: a subscription feed's whole point is that its window
# rolls forward on its own (see `default_ics_window`) rather than being
# pinned to whatever range was true when the URL was generated.
@app.get("/api/conjunctions.ics")
def conjunctions_ics(
    birth_date: Annotated[str, Query(description="YYYY-MM-DD")],
    birth_time: Annotated[str, Query(description="HH:MM, 24h, local to birth place")],
    birth_place: Annotated[str | None, Query()] = None,
    latitude: Annotated[float | None, Query(ge=-90, le=90)] = None,
    longitude: Annotated[float | None, Query(ge=-180, le=180)] = None,
    name: Annotated[str | None, Query()] = None,
    bodies: Annotated[
        list[TransitingBody] | None,
        Query(description="Repeat the param per body, e.g. ?bodies=moon&bodies=sun"),
    ] = None,
) -> PlainTextResponse:
    """A public, subscribable .ics feed: 1 month back, 6 months ahead.

    Meant for pasting into a calendar client's "subscribe by URL" field
    (Google Calendar, Outlook, Apple Calendar all support this), not for the
    web frontend, which already gets richer per-search results from
    ``/api/conjunctions``. No auth: this endpoint is a GET with everything it
    needs in the query string on purpose, because that is the only shape a
    calendar client's "add by URL" feature can drive — the request/response
    is otherwise identical in spirit to POST /api/conjunctions.
    """
    try:
        birth_info = BirthInfo(
            birth_date=birth_date,  # type: ignore[arg-type]
            birth_time=birth_time,  # type: ignore[arg-type]
            birth_place=birth_place,
            latitude=latitude,
            longitude=longitude,
            name=name,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    selected_bodies: list[TransitingBody] = (
        [b for b in ("moon", "sun") if b in bodies] if bodies else ["moon", "sun"]
    )
    if not selected_bodies:
        raise HTTPException(
            status_code=422,
            detail="Select at least one transiting body ('moon' and/or 'sun').",
        )

    try:
        location = resolve_location(
            place=birth_info.birth_place,
            latitude=birth_info.latitude,
            longitude=birth_info.longitude,
        )
        chart = compute_natal_chart(birth_info, location=location)
        start_date, end_date = default_ics_window()
        events = find_conjunctions_for_dates(
            chart, start_date=start_date, end_date=end_date, bodies=selected_bodies
        )
    except LocationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except EphemerisError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    calendar_name = f"{chart.name}: Conjunctions" if chart.name else "Conjunctions"
    ics_text = build_ics_feed(chart, events, calendar_name)
    return PlainTextResponse(
        content=ics_text,
        media_type="text/calendar; charset=utf-8",
        headers={
            "Content-Disposition": 'inline; filename="conjunctions.ics"',
            # Subscribed feeds are re-fetched periodically by the calendar
            # client, not once — a long cache would show a stale window.
            "Cache-Control": "public, max-age=3600",
        },
    )


# AWS Lambda entry point (API Gateway proxy integration). Unused locally.
handler = Mangum(app, lifespan="off")
