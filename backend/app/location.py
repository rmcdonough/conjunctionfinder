"""Place-name geocoding and IANA timezone resolution.

Two ways in:
  * a free-text place name, geocoded with geopy's Nominatim, or
  * explicit latitude/longitude, in which case no network call happens.

Either way we end up with (lat, lon, display name, IANA timezone), which is
everything the natal-chart maths needs.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache

from geopy.exc import GeocoderServiceError, GeocoderTimedOut, GeocoderUnavailable
from geopy.geocoders import Nominatim
from timezonefinder import TimezoneFinder

GEOCODER_USER_AGENT = os.environ.get(
    "GEOCODER_USER_AGENT", "astrology-conjunction-finder/1.0"
)
GEOCODER_TIMEOUT = float(os.environ.get("GEOCODER_TIMEOUT", "10"))


class LocationError(ValueError):
    """Raised when a place name cannot be resolved to coordinates + timezone."""


@dataclass(frozen=True)
class ResolvedLocation:
    latitude: float
    longitude: float
    display_name: str
    timezone: str


@lru_cache(maxsize=1)
def _geocoder() -> Nominatim:
    return Nominatim(user_agent=GEOCODER_USER_AGENT, timeout=GEOCODER_TIMEOUT)


@lru_cache(maxsize=1)
def _timezone_finder() -> TimezoneFinder:
    # in_memory=True keeps lookups fast across requests (a few MB of RAM).
    return TimezoneFinder(in_memory=True)


@lru_cache(maxsize=256)
def geocode_place(place: str) -> tuple[float, float, str]:
    """Geocode a free-text place name to ``(lat, lon, display_name)``."""
    query = place.strip()
    if not query:
        raise LocationError("Birth place must not be empty.")
    try:
        location = _geocoder().geocode(query)
    except (GeocoderTimedOut, GeocoderUnavailable, GeocoderServiceError) as exc:
        raise LocationError(
            f"Geocoding service unavailable while looking up {query!r}: {exc}. "
            "Try again, or supply latitude/longitude directly."
        ) from exc
    if location is None:
        raise LocationError(
            f"Could not find a place matching {query!r}. Try a more specific "
            "name (e.g. 'Toronto, Ontario, Canada') or supply latitude/longitude."
        )
    return float(location.latitude), float(location.longitude), str(location.address)


def timezone_for(lat: float, lon: float) -> str:
    """IANA timezone name for a coordinate pair."""
    tz = _timezone_finder().timezone_at(lat=lat, lng=lon)
    if tz is None:
        raise LocationError(
            f"Could not determine a timezone for latitude {lat}, longitude {lon} "
            "(is it in the middle of an ocean?)."
        )
    return tz


def resolve_location(
    place: str | None = None,
    latitude: float | None = None,
    longitude: float | None = None,
) -> ResolvedLocation:
    """Resolve either explicit coordinates or a place name into a location.

    Explicit coordinates win when both are supplied — the caller was explicit,
    so we skip the network round trip and only use ``place`` as a display label.
    """
    if latitude is not None and longitude is not None:
        display = place.strip() if place and place.strip() else (
            f"{latitude:.4f}, {longitude:.4f}"
        )
        return ResolvedLocation(
            latitude=float(latitude),
            longitude=float(longitude),
            display_name=display,
            timezone=timezone_for(float(latitude), float(longitude)),
        )

    if not place or not place.strip():
        raise LocationError(
            "Provide either a birth place name or both latitude and longitude."
        )

    lat, lon, display = geocode_place(place)
    return ResolvedLocation(
        latitude=lat,
        longitude=lon,
        display_name=display,
        timezone=timezone_for(lat, lon),
    )
