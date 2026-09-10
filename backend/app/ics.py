"""Build an RFC 5545 multi-event .ics calendar feed for conjunction events.

Mirrors the per-event VEVENT shape the frontend's ``src/ics.ts`` already
builds client-side for a single event's "add to calendar" link (same
30-minute visible duration, same UID scheme, UTC timestamps throughout) but
emits every event into one VCALENDAR — that's the difference between a
one-off download and something a calendar client can subscribe to.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from .schemas import ConjunctionEvent, NatalChart

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
    """Lowercase, hyphenated fragment for UIDs — mirrors the frontend's slugify."""
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
        body_name = BODY_NAME[event.transiting_body]
        start = datetime.fromisoformat(event.utc)
        end = start + EVENT_DURATION
        dtstart = _ics_stamp(start)
        summary = f"{event.natal_key} conjunct Natal {body_name}"
        description = (
            f"Transiting {body_name} conjuncts natal {event.natal_key} "
            f"({event.natal_label})."
        )
        uid = (
            f"{_slugify(event.natal_key)}-{_slugify(body_name)}-{dtstart}"
            "@astrology-conjunction-finder"
        )
        lines += [
            "BEGIN:VEVENT",
            f"UID:{uid}",
            f"DTSTAMP:{now_stamp}",
            f"DTSTART:{dtstart}",
            f"DTEND:{_ics_stamp(end)}",
            f"SUMMARY:{_escape(summary)}",
            f"DESCRIPTION:{_escape(description)}",
            "END:VEVENT",
        ]

    lines.append("END:VCALENDAR")
    return "\r\n".join(lines) + "\r\n"
