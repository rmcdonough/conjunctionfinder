"""Build RFC 5545 .ics calendars for conjunction events.

Two entry points share the same per-event VEVENT builder:

* ``build_ics_feed`` — many events in one VCALENDAR, for the public
  subscription feed (``GET /api/conjunctions.ics``).
* ``build_single_event_ics`` — exactly one event in its own VCALENDAR, for
  the per-row "Calendar invite" download in the results table
  (``GET /api/conjunction-event.ics``). This exists because the frontend
  used to build this file entirely client-side as a ``data:`` URI, which
  iOS Safari cannot download (it does not honour the anchor ``download``
  attribute on ``data:`` URIs) — serving it as a real HTTP resource fixes
  that, since tapping a link to a ``text/calendar`` resource is something
  iOS Safari has supported natively since iOS 5.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from .schemas import ConjunctionEvent, NatalChart, TransitingBody

BODY_NAME = {"moon": "Moon", "sun": "Sun"}

# Conjunctions are instants; give each calendar entry a short visible span
# rather than a zero-length event, which several calendar UIs render oddly.
EVENT_DURATION = timedelta(minutes=30)


def _escape(text: str) -> str:
    """RFC 5545 §3.3.11 text escaping: backslash, semicolon, comma, newline."""
    return (
        text.replace("\\", "\\\\")
        .replace(";", "\\;")
        .replace(",", "\\,")
        .replace("\r\n", "\\n")
        .replace("\n", "\\n")
    )


def _slugify(text: str) -> str:
    """Lowercase, hyphenated fragment for UIDs/filenames — mirrors the
    frontend's own ``slugify`` in ``frontend/src/ics.ts``."""
    out: list[str] = []
    prev_dash = False
    for ch in text.lower():
        if ch.isalnum():
            out.append(ch)
            prev_dash = False
        elif not prev_dash:
            out.append("-")
            prev_dash = True
    return "".join(out).strip("-")


def _ics_stamp(dt: datetime) -> str:
    """Aware datetime -> ICS basic UTC format, e.g. ``20260615T143000Z``."""
    return dt.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _vevent_lines(
    transiting_body: TransitingBody,
    natal_key: str,
    natal_label: str,
    utc_iso: str,
    now_stamp: str,
) -> list[str]:
    """The BEGIN:VEVENT..END:VEVENT block for one conjunction, given just the
    fields the frontend already has on hand (no chart/ephemeris needed)."""
    body_name = BODY_NAME[transiting_body]
    start = datetime.fromisoformat(utc_iso)
    end = start + EVENT_DURATION
    dtstart = _ics_stamp(start)
    summary = f"{natal_key} conjunct Natal {body_name}"
    description = f"Transiting {body_name} conjuncts natal {natal_key} ({natal_label})."
    uid = f"{_slugify(natal_key)}-{_slugify(body_name)}-{dtstart}@astrology-conjunction-finder"
    return [
        "BEGIN:VEVENT",
        f"UID:{uid}",
        f"DTSTAMP:{now_stamp}",
        f"DTSTART:{dtstart}",
        f"DTEND:{_ics_stamp(end)}",
        f"SUMMARY:{_escape(summary)}",
        f"DESCRIPTION:{_escape(description)}",
        "END:VEVENT",
    ]


def build_ics_feed(
    chart: NatalChart, events: list[ConjunctionEvent], calendar_name: str
) -> str:
    """Render every event into one VCALENDAR. CRLF line endings per RFC 5545."""
    now_stamp = _ics_stamp(datetime.now(timezone.utc))

    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//Astrology Conjunction Finder//EN",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
        f"X-WR-CALNAME:{_escape(calendar_name)}",
        # Hints some clients (Google Calendar, Outlook) use when deciding how
        # often to re-poll a subscribed feed. Not binding on any client, but
        # harmless to include, and this feed's content is genuinely time-
        # varying (see transits.default_ics_window), so a hint is honest.
        "X-PUBLISHED-TTL:PT12H",
        "REFRESH-INTERVAL;VALUE=DURATION:PT12H",
    ]

    for event in events:
        lines += _vevent_lines(
            event.transiting_body, event.natal_key, event.natal_label, event.utc, now_stamp
        )

    lines.append("END:VCALENDAR")
    return "\r\n".join(lines) + "\r\n"


def build_single_event_ics(
    transiting_body: TransitingBody, natal_key: str, natal_label: str, utc_iso: str
) -> str:
    """One conjunction event as its own one-VEVENT VCALENDAR.

    Deliberately stateless — no birth data, chart, or ephemeris involved.
    The frontend already computed everything needed for the event when it
    ran the original search; this just re-renders those same fields as an
    .ics file server-side instead of client-side.
    """
    now_stamp = _ics_stamp(datetime.now(timezone.utc))
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//Astrology Conjunction Finder//EN",
        "CALSCALE:GREGORIAN",
        *_vevent_lines(transiting_body, natal_key, natal_label, utc_iso, now_stamp),
        "END:VCALENDAR",
    ]
    return "\r\n".join(lines) + "\r\n"


def single_event_ics_filename(
    transiting_body: TransitingBody, natal_key: str, utc_iso: str
) -> str:
    """Suggested download filename — mirrors the frontend's ``icsFileName``."""
    body_name = BODY_NAME[transiting_body]
    date_stamp = utc_iso[:10]  # YYYY-MM-DD
    return f"{_slugify(natal_key)}-conjunct-natal-{_slugify(body_name)}-{date_stamp}.ics"
