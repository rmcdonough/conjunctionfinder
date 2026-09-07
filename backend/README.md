# Backend — Astrology Conjunction Finder API

FastAPI service that computes a natal chart with the Swiss Ephemeris
(`pyswisseph`) and finds every transiting Moon/Sun conjunction with a natal
point over a window of up to 12 months.

Stateless: no auth, no database, nothing persisted between requests.

## Layout

```
backend/
  app/
    main.py        FastAPI app + routes + CORS; exports `handler` for Lambda
    schemas.py     Pydantic request/response models and all input validation
    natal.py       birth data -> natal points (planets, nodes, house cusps)
    transits.py    conjunction search (mooncross_ut / solcross_ut)
    location.py    Nominatim geocoding + timezonefinder IANA lookup
    ephemeris.py   thin pyswisseph wrappers (JD conversion, labels, crossings)
  ephe/            Swiss Ephemeris data files (see "Ephemeris data" below)
  tests/           pytest suite
  template.yaml    AWS SAM scaffolding (NOT deployed — see top-level README)
  requirements.txt
```

## Run locally

```bash
cd backend
uv venv .venv
uv pip install -r requirements.txt
.venv/bin/uvicorn app.main:app --reload --port 8000
```

`uv pip install` installs into `.venv` automatically once it exists. If you'd
rather activate the venv (`source .venv/bin/activate`), the bare
`uvicorn app.main:app --reload --port 8000` works too.

Interactive docs: <http://localhost:8000/docs>. Health check:
<http://localhost:8000/api/health>.

### Environment variables

| Variable | Default | Purpose |
| --- | --- | --- |
| `ALLOWED_ORIGINS` | `http://localhost:5173,http://127.0.0.1:5173` | Comma-separated CORS origins |
| `EPHE_PATH` | `backend/ephe` | Where the `.se1` ephemeris files live |
| `GEOCODER_USER_AGENT` | `astrology-conjunction-finder/1.0` | Sent to Nominatim (its usage policy requires an identifying UA) |
| `GEOCODER_TIMEOUT` | `10` | Geocoder timeout, seconds |

## API

### `POST /api/natal-chart`

Body — either `birth_place` (geocoded server-side) or both `latitude` and
`longitude`; supplying both means the coordinates win and no geocoding request
is made.

```json
{
  "birth_date": "1971-03-15",
  "birth_time": "04:30",
  "birth_place": "Toronto, Ontario, Canada",
  "latitude": 43.6532,
  "longitude": -79.3832,
  "name": "Optional display name"
}
```

Returns the resolved place, latitude/longitude, IANA timezone, the birth
instant in both local time and UTC, its Julian Day, and 25 natal points: Sun,
Moon, Mercury, Venus, Mars, Jupiter, Saturn, Uranus, Neptune, Pluto, Chiron,
Dragon's Head (mean node) and Dragon's Tail (node + 180°), plus the 12 Placidus
house cusps. Each point carries its longitude, sign, degree-in-sign, a
`25°16′00″ Leo`-style label, a retrograde flag and the longitude speed in
°/day (`null` for house cusps).

### `POST /api/conjunctions`

The same birth body, plus the search window and body selection:

```json
{
  "birth_date": "1971-03-15",
  "birth_time": "04:30",
  "latitude": 43.6532,
  "longitude": -79.3832,
  "start_year": 2026,
  "start_month": 6,
  "end_year": 2026,
  "end_month": 6,
  "bodies": ["moon", "sun"]
}
```

`bodies` defaults to `["moon", "sun"]`. The window is inclusive of whole
calendar months and capped at 12 months.

Returns the natal chart **and** the chronologically sorted event list in one
round trip, so the frontend needs no second request. Each event has the UTC
timestamp, the same instant in the birth location's timezone, which transiting
body it was, the natal point's key/label/longitude, and the transiting body's
*verified* longitude at that instant.

### Errors

- `422` — Pydantic validation: bad dates, missing place *and* coordinates,
  out-of-range lat/lon, empty `bodies`, end month before start month, or a
  window longer than 12 months.
- `400` — a place name that cannot be geocoded, an unreachable geocoding
  service, a coordinate with no resolvable timezone, or an ephemeris failure.

Both shapes put a human-readable message in the response body, which the
frontend surfaces verbatim.

### Try it with curl

```bash
curl -s -X POST http://localhost:8000/api/conjunctions \
  -H 'Content-Type: application/json' \
  -d '{"birth_date":"1971-03-15","birth_time":"04:30",
       "latitude":43.6532,"longitude":-79.3832,
       "start_year":2026,"start_month":6,"end_year":2026,"end_month":6,
       "bodies":["moon","sun"]}' | python3 -m json.tool | head -40
```

## How it works

1. **Location** — `geopy`'s Nominatim turns a place name into coordinates (or
   you pass them directly); `timezonefinder` turns coordinates into an IANA
   timezone name.
2. **Time** — the birth date/time is interpreted as *local wall clock* in that
   timezone via `zoneinfo`, which applies the DST/UTC-offset rules that were
   actually in force on the birth date, then converted to UTC and to a Julian
   Day with `swe.julday`.
3. **Chart** — `swe.calc_ut(jd, body, FLG_SWIEPH | FLG_SPEED)` per body;
   element 0 of the result is ecliptic longitude and element 3 is longitude
   speed, so a negative speed means retrograde. House cusps come from
   `swe.houses(jd, lat, lon, b'P')` (Placidus).
4. **Search** — for each natal longitude, `swe.mooncross_ut` /
   `swe.solcross_ut` return the next instant the transiting body crosses it.
   The search cursor then hops forward — 25 days for the Moon (which returns to
   a longitude every ~27.32 days) and 340 days for the Sun (~365.24 days) — and
   asks again, until it passes the end of the window. Both hops are shorter
   than the return period, so no crossing can be skipped, and long enough to
   clear the crossing just found, so none is reported twice.
5. **Verify** — every crossing is re-checked by recomputing the transiting
   body's longitude at the returned instant; it is only reported if it lands
   within 1 arcminute of the natal target. (In practice the solver is accurate
   to ~1e-8°.)

### pyswisseph API notes

Verified empirically against **pyswisseph 2.10.03** — both of these differ from
what the C API docs would lead you to expect:

- `swe.houses()` returns `(cusps, ascmc)` where `cusps` is a **12-tuple indexed
  from 0**: `cusps[0]` is the 1st-house cusp (equal to `ascmc[0]`, the
  Ascendant) and `cusps[9]` is the 10th (equal to `ascmc[1]`, the MC). The C
  API instead uses a 13-element array with an unused element 0 and houses in
  `[1..12]`. `app/ephemeris.py:house_cusps` normalises to a plain 12-element
  list in house order, and `tests/test_ephemeris.py` pins this so an upgrade
  that changes it fails loudly.
- Swiss Ephemeris global state — **including the ephemeris file search path** —
  is **thread-local** in this build. A `set_ephe_path()` call on the main
  thread is invisible to FastAPI's threadpool workers, where Chiron then raises
  "file not found" and other bodies silently fall back to the lower-precision
  built-in Moshier model. `app/ephemeris.py` therefore re-sets the path once per
  thread (`ensure_ephe_path`), guarded by a `threading.local` flag because
  `set_ephe_path` closes any open ephemeris files.

### Ephemeris data

`ephe/` holds the Swiss Ephemeris data files for 1800–2400 AD, committed so the
repo runs out of the box:

| File | Contents |
| --- | --- |
| `semo_18.se1` | Moon |
| `sepl_18.se1` | Planets |
| `seas_18.se1` | Asteroids — **required for Chiron** |

They come from <https://github.com/aloistr/swisseph/tree/master/ephe>. Without
them Chiron cannot be computed at all and everything else quietly degrades to
the Moshier fallback, so don't delete them; point `EPHE_PATH` elsewhere if you
keep them outside the repo.

## Tests

```bash
cd backend
.venv/bin/python -m pytest
```

53 tests covering: the pyswisseph API shape we depend on (including the two
surprises above), longitude/label/sign-boundary maths, Julian Day round trips,
natal chart structure and invariants (nodes exactly opposite, opposite cusps
180° apart, 1st cusp == Ascendant, retrograde derived from speed), local-time
interpretation including historical DST, the conjunction search (every event
verified on target, sorted, inside the window, Moon hits all 25 points each
month, Sun hits each exactly once per year), and both endpoints plus every
validation error path.

The suite is offline by default. One test does a real Nominatim lookup and is
skipped unless you ask for it:

```bash
RUN_NETWORK_TESTS=1 .venv/bin/python -m pytest
```

## AWS deployment

`template.yaml` is SAM scaffolding only — never deployed, never validated
against CloudFormation. `app/main.py` already exports the Mangum adapter as
`handler`, so the same code runs locally under uvicorn and on Lambda. See
"Future work" in the top-level README.
