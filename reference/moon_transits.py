"""
moon_transits.py
────────────────
Find every moment in a given month when the Moon conjuncts each natal
position in the chart below.

Usage:
    python moon_transits.py <month>           # uses current year (2026)
    python moon_transits.py <year> <month>    # explicit year

Examples:
    python moon_transits.py 6
    python moon_transits.py 2026 6

Requires:  pip install libephemeris
           (NASA JPL DE440-powered, pyswisseph-compatible)
"""

import sys
import calendar
from datetime import datetime, timezone, timedelta

import libephemeris as swe

# ── Timezone ───────────────────────────────────────────────────────────────
EDT = timezone(timedelta(hours=-4), name="EDT")

# ── Zodiac reference ───────────────────────────────────────────────────────
ZODIAC_SIGNS = [
    "Aries", "Taurus", "Gemini", "Cancer",
    "Leo", "Virgo", "Libra", "Scorpio",
    "Sagittarius", "Capricorn", "Aquarius", "Pisces",
]

SIGN_BASE = {sign: i * 30.0 for i, sign in enumerate(ZODIAC_SIGNS)}

# ── Natal positions ────────────────────────────────────────────────────────
# Format: (Key label, sign, degrees, minutes, seconds, retrograde flag)
# Longitude = sign_base + degrees + minutes/60 + seconds/3600
# (The original table omits seconds for a few entries; those default to 0.)

RAW_NATAL = [
    ("Moon",          "Leo",         25,  16,  0,  False),
    ("12th Temple",   "Virgo",        8,  55,  0,  False),
    ("1st Temple",    "Libra",        2,   4,  0,  False),
    ("Pluto",         "Libra",       10,  48,  0,  True),
    ("2nd Temple",    "Libra",       25,  44,  0,  False),
    ("Uranus",        "Scorpio",      6,  41,  0,  True),
    ("Dragon's Head", "Scorpio",     13,  44,  0,  False),
    ("3rd Temple",    "Scorpio",     25,  56,  0,  False),
    ("Neptune",       "Sagittarius", 13,  58,  0,  False),
    ("4th Temple",    "Capricorn",    2,  45,  0,  False),
    ("5th Temple",    "Aquarius",     9,  14,  0,  False),
    ("Venus",         "Aquarius",    28,  50,  0,  False),
    ("Mercury",       "Pisces",       7,  27,  0,  False),
    ("6th Temple",    "Pisces",       8,  55,  0,  False),
    ("Sun",           "Pisces",      23,  38,  0,  False),
    ("7th Temple",    "Aries",        2,   4,  0,  False),
    ("Chiron",        "Aries",       25,  39,  0,  False),
    ("8th Temple",    "Aries",       25,  44,  0,  False),
    ("Jupiter",       "Aries",       27,  13,  0,  False),
    ("Dragon's Tail", "Taurus",      13,  44,  0,  False),
    ("9th Temple",    "Taurus",      25,  56,  0,  False),
    ("Mars",          "Gemini",      28,   5,  0,  False),
    ("10th Temple",   "Cancer",       2,  45,  0,  False),
    ("Saturn",        "Cancer",      26,  11,  0,  True),
    ("11th Temple",   "Leo",          9,  14,  0,  False),
]

def natal_longitude(sign: str, deg: int, minutes: int, seconds: int) -> float:
    """Convert sign + d/m/s to decimal ecliptic longitude (0–360°)."""
    return SIGN_BASE[sign] + deg + minutes / 60.0 + seconds / 3600.0

def lon_to_label(lon: float) -> str:
    """Format a decimal longitude as e.g. '25°16′00″ Leo'."""
    sign_idx = int(lon // 30)
    deg_in_sign = lon % 30
    d = int(deg_in_sign)
    m = int((deg_in_sign - d) * 60)
    s = int(round(((deg_in_sign - d) * 60 - m) * 60))
    return f"{d}°{m:02d}′{s:02d}″ {ZODIAC_SIGNS[sign_idx]}"

def jd_to_datetime(jd: float, tz=timezone.utc) -> datetime:
    """Convert a Julian Day number (UT) to a timezone-aware datetime."""
    year, month, day, frac_h = swe.revjul(jd, 1)
    hour   = int(frac_h)
    minute = int((frac_h - hour) * 60)
    second = int(round(((frac_h - hour) * 60 - minute) * 60))
    # clamp rounding edge-cases
    if second == 60:
        second = 59
    dt_utc = datetime(year, month, day, hour, minute, second, tzinfo=timezone.utc)
    return dt_utc.astimezone(tz) if tz != timezone.utc else dt_utc

# ── Build the natal table ──────────────────────────────────────────────────
NATAL_POINTS = []
for key, sign, deg, minutes, seconds, retro in RAW_NATAL:
    lon = natal_longitude(sign, deg, minutes, seconds)
    label = f"{key} {'(R) ' if retro else ''}— {lon_to_label(lon)}"
    NATAL_POINTS.append((key, lon, label, retro))

# ── Main search ────────────────────────────────────────────────────────────
def find_moon_transits(year: int, month: int) -> None:
    days_in_month = calendar.monthrange(year, month)[1]
    month_name    = calendar.month_name[month]

    jd_start = swe.julday(year, month, 1, 0.0)
    jd_end   = swe.julday(year, month, days_in_month, 23.9999)

    print(f"\n🔭  Moon transits over natal positions — {month_name} {year}")
    print(f"    Searching {days_in_month} days …\n")

    all_events: list[tuple[float, str, str, str]] = []  # (jd, key, label, verified_lon)

    for key, target_lon, label, _retro in NATAL_POINTS:
        jd_search = jd_start
        while jd_search < jd_end:
            try:
                jd_cross = swe.mooncross_ut(target_lon, jd_search)
            except RuntimeError:
                break

            if jd_cross >= jd_end:
                break

            # Verify actual Moon longitude at crossing moment
            pos, _ = swe.calc_ut(jd_cross, swe.MOON, swe.FLG_SPEED)
            verified = lon_to_label(pos[0])

            all_events.append((jd_cross, key, label, verified))

            # Advance past this crossing — Moon laps the zodiac in ~27.3 days,
            # so 25 days safely skips to near the next opportunity.
            jd_search = jd_cross + 25.0

    if not all_events:
        print(f"  No Moon conjunctions found in {month_name} {year}.\n")
        return

    # Sort chronologically
    all_events.sort(key=lambda e: e[0])

    print(f"  {'#':<4}  {'UTC Date & Time':<32}  {'Toronto (EDT)':<32}  {'Natal Point'}")
    print("  " + "─" * 110)

    for i, (jd, key, label, verified) in enumerate(all_events, 1):
        dt_utc = jd_to_datetime(jd)
        dt_edt = jd_to_datetime(jd, EDT)

        utc_str = dt_utc.strftime("%a %d %b %Y  %H:%M:%S UTC")
        edt_str = dt_edt.strftime("%a %d %b %Y  %H:%M:%S EDT")

        print(f"  {i:<4}  {utc_str:<32}  {edt_str:<32}  {label}")
        print(f"  {'':4}  {'':32}  {'Verified Moon lon:':32}  {verified}")
        print()

    print(f"  Total transits in {month_name} {year}: {len(all_events)}\n")


# ── CLI entry point ────────────────────────────────────────────────────────
if __name__ == "__main__":
    args = sys.argv[1:]

    if len(args) == 1:
        # python moon_transits.py <month>
        try:
            month = int(args[0])
            year  = 2026          # default year
        except ValueError:
            sys.exit("Usage: python moon_transits.py [year] <month>  (month as 1–12)")

    elif len(args) == 2:
        # python moon_transits.py <year> <month>
        try:
            year  = int(args[0])
            month = int(args[1])
        except ValueError:
            sys.exit("Usage: python moon_transits.py [year] <month>  (month as 1–12)")

    else:
        sys.exit("Usage: python moon_transits.py [year] <month>  (month as 1–12)")

    if not 1 <= month <= 12:
        sys.exit("Month must be between 1 and 12.")

    find_moon_transits(year, month)
