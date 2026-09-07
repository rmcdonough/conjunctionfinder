"""Pydantic request/response models for the public API."""

from __future__ import annotations

import calendar
from datetime import date, time
from typing import Annotated, Literal

from pydantic import BaseModel, Field, field_validator, model_validator

TransitingBody = Literal["moon", "sun"]

MAX_RANGE_MONTHS = 12


class BirthInfo(BaseModel):
    """Birth data. Either ``birth_place`` or both lat/lon must be supplied."""

    birth_date: date = Field(..., description="Birth date, YYYY-MM-DD")
    birth_time: time = Field(..., description="Local birth time, HH:MM (24h)")
    birth_place: str | None = Field(
        None,
        description="Free-text place name, geocoded server-side (e.g. 'Toronto, Canada')",
    )
    latitude: Annotated[float, Field(ge=-90, le=90)] | None = Field(
        None, description="Optional explicit latitude, overrides geocoding"
    )
    longitude: Annotated[float, Field(ge=-180, le=180)] | None = Field(
        None, description="Optional explicit longitude, overrides geocoding"
    )
    name: str | None = Field(
        None, description="Optional display name; never stored anywhere"
    )

    @field_validator("birth_time", mode="before")
    @classmethod
    def _accept_hh_mm(cls, value: object) -> object:
        # Browsers send "HH:MM" from <input type="time">; pydantic handles that,
        # but be forgiving about surrounding whitespace.
        if isinstance(value, str):
            return value.strip()
        return value

    @model_validator(mode="after")
    def _require_place_or_coords(self) -> "BirthInfo":
        has_coords = self.latitude is not None and self.longitude is not None
        has_place = bool(self.birth_place and self.birth_place.strip())
        if not has_coords and not has_place:
            raise ValueError(
                "Provide either birth_place, or both latitude and longitude."
            )
        if (self.latitude is None) != (self.longitude is None):
            raise ValueError(
                "latitude and longitude must be supplied together."
            )
        return self


class ConjunctionsRequest(BirthInfo):
    """Birth data plus the search window and which transiting bodies to use."""

    start_year: Annotated[int, Field(ge=1800, le=2399)]
    start_month: Annotated[int, Field(ge=1, le=12)]
    end_year: Annotated[int, Field(ge=1800, le=2399)]
    end_month: Annotated[int, Field(ge=1, le=12)]
    bodies: list[TransitingBody] = Field(
        default_factory=lambda: ["moon", "sun"],
        description="Transiting bodies to search; defaults to both.",
    )

    @field_validator("bodies")
    @classmethod
    def _dedupe_bodies(cls, value: list[str]) -> list[str]:
        if not value:
            raise ValueError("Select at least one transiting body ('moon' and/or 'sun').")
        # Preserve a stable order, drop duplicates.
        return [b for b in ("moon", "sun") if b in value]

    @model_validator(mode="after")
    def _validate_range(self) -> "ConjunctionsRequest":
        start_index = self.start_year * 12 + (self.start_month - 1)
        end_index = self.end_year * 12 + (self.end_month - 1)
        if end_index < start_index:
            raise ValueError("End month must not be before start month.")
        span = end_index - start_index + 1
        if span > MAX_RANGE_MONTHS:
            raise ValueError(
                f"Date range spans {span} months; the maximum is {MAX_RANGE_MONTHS}."
            )
        return self

    @property
    def month_span(self) -> int:
        return (
            self.end_year * 12
            + (self.end_month - 1)
            - (self.start_year * 12 + (self.start_month - 1))
            + 1
        )

    @property
    def range_start_date(self) -> date:
        return date(self.start_year, self.start_month, 1)

    @property
    def range_end_date(self) -> date:
        last_day = calendar.monthrange(self.end_year, self.end_month)[1]
        return date(self.end_year, self.end_month, last_day)


class NatalPoint(BaseModel):
    key: str = Field(..., description="e.g. 'Sun', 'Dragon's Head', '7th House'")
    category: Literal["luminary", "planet", "node", "house"]
    longitude: float = Field(..., description="Ecliptic longitude in degrees, [0, 360)")
    sign: str
    degree_in_sign: float
    label: str = Field(..., description="e.g. '25°16′00″ Leo'")
    retrograde: bool
    speed: float | None = Field(
        None, description="Longitude speed in deg/day (None for house cusps)"
    )


class NatalChart(BaseModel):
    name: str | None = None
    points: list[NatalPoint]
    latitude: float
    longitude: float
    resolved_place: str
    timezone: str = Field(..., description="IANA timezone of the birth place")
    birth_datetime_local: str
    birth_datetime_utc: str
    julian_day: float


class ConjunctionEvent(BaseModel):
    utc: str = Field(..., description="ISO 8601 UTC timestamp of the conjunction")
    local: str = Field(
        ..., description="ISO 8601 timestamp in the birth location's timezone"
    )
    julian_day: float
    transiting_body: TransitingBody
    natal_key: str
    natal_label: str
    natal_longitude: float
    transiting_longitude: float = Field(
        ..., description="Verified longitude of the transiting body at that moment"
    )
    transiting_label: str


class ConjunctionsResponse(BaseModel):
    natal_chart: NatalChart
    events: list[ConjunctionEvent]
    event_count: int
    range_start: str
    range_end: str
    bodies: list[TransitingBody]
