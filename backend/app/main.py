"""FastAPI application.

The same ASGI app object runs two ways:
  * locally:  ``uvicorn app.main:app --reload --port 8000``
  * on Lambda: via the Mangum adapter exported as ``handler`` (see template.yaml)

Fully stateless — no auth, no database, nothing persisted between requests.
"""

from __future__ import annotations

import os

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from mangum import Mangum

from .ephemeris import EphemerisError
from .location import LocationError, resolve_location
from .natal import compute_natal_chart
from .schemas import (
    BirthInfo,
    ConjunctionsRequest,
    ConjunctionsResponse,
    NatalChart,
)
from .transits import find_conjunctions

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


# AWS Lambda entry point (API Gateway proxy integration). Unused locally.
handler = Mangum(app, lifespan="off")
