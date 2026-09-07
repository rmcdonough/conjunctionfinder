# Astrology Conjunction Finder — Build Spec

## Goal
A web app where a user enters their birth date, time, and place. The app
computes their natal chart, then finds every moment within a chosen date
range (up to 12 months) where the transiting Moon and/or Sun conjuncts a
natal point (planet, luminary, node, Chiron, or house cusp). Output is a
sorted list of conjunction events. No auth, no database — fully stateless,
request/response.

Reference prototype: `reference/moon_transits.py` in this repo (already
copied in) — a hardcoded-natal-chart script that finds Moon conjunctions
for one month using a Swiss-Ephemeris-style API (`julday`, `calc_ut`,
`mooncross_ut`, `revjul`). It imports a fictional `libephemeris` package;
the REAL package with an (almost) identical API is **`pyswisseph`**
(`import swisseph as swe`) — same function names: `swe.julday`,
`swe.calc_ut`, `swe.mooncross_ut`, `swe.solcross_ut`, `swe.revjul`,
`swe.houses`. Verified working via `pip install pyswisseph`.

## Architecture

**Backend**: Python, FastAPI app wrapped for AWS Lambda via Mangum, so the
exact same code runs locally (`uvicorn app.main:app --reload`) and deploys
to Lambda later (API Gateway + Lambda, via an AWS SAM template). Priority
right now is **running locally** — defer actual AWS deployment.

**Frontend**: React + Vite (JS or TS, your choice — TS preferred), calling
the backend over HTTP. No server-side rendering needed.

## Backend — detailed requirements

Directory: `backend/`

Dependencies (already verified installable): `fastapi`, `uvicorn`,
`mangum`, `pyswisseph`, `timezonefinder`, `geopy`, `pydantic`.

### Natal chart computation
Input: birth date (YYYY-MM-DD), birth time (HH:MM, 24h), birth place
(free-text city/place name — geocode server-side with `geopy`
Nominatim, OR accept explicit lat/lon if provided instead — support both).

Steps:
1. Geocode place name → (lat, lon) if lat/lon not supplied directly.
2. Look up IANA timezone for (lat, lon) via `timezonefinder`.
3. Interpret the birth date+time as LOCAL time in that timezone (use
   Python `zoneinfo` — this correctly handles historical DST/UTC-offset
   rules for the birth date, unlike a fixed offset). Convert to UTC.
4. Convert UTC datetime → Julian Day via `swe.julday` (UT).
5. Compute natal longitudes for: Sun, Moon, Mercury, Venus, Mars, Jupiter,
   Saturn, Uranus, Neptune, Pluto, Chiron, Mean Node ("Dragon's Head") and
   its opposite point ("Dragon's Tail" = Node + 180°), via `swe.calc_ut`
   with the appropriate planet constants (`swe.SUN`, `swe.MOON`, ...,
   `swe.CHIRON`, `swe.MEAN_NODE`).
6. Compute house cusps (12 of them) via `swe.houses(jd, lat, lon, b'P')`
   for Placidus. Label them "1st House" .. "12th House" (cusp longitudes
   are `cusps[1..12]` — index 0 is unused/ASC duplicate depending on
   version; verify against `swe.houses` docs/behavior empirically and
   note it in code comments).
7. Also flag retrograde status per planet using the speed component from
   `calc_ut` with `swe.FLG_SPEED` (negative speed = retrograde). Not
   applicable to house cusps or nodes' printed retrograde flag rules —
   match the spirit of the reference script's `RAW_NATAL` retrograde flags
   but derive it live from computed speed rather than hardcoding.

Return this natal point list (key, longitude, sign+deg label, retrograde
bool) — this is the reusable "natal chart" object.

### Conjunction search
Input: the natal chart (or raw birth info to recompute it), a start
year/month and end year/month (inclusive range, max 12 months span,
validate and reject longer), and which transiting bodies to search
(`"moon"`, `"sun"`, or both — default both).

For each requested transiting body and each natal point, replicate the
reference script's approach:
- Moon: `swe.mooncross_ut(target_lon, jd_search)`
- Sun: `swe.solcross_ut(target_lon, jd_search)`
- Step `jd_search` forward past each found crossing by a safe margin
  (Moon ~25 days per the reference script; Sun should step ~340 days
  since the Sun only conjuncts each natal point once per year — pick a
  safe value and justify it in a comment) until past `jd_end`.
- Verify each crossing by recomputing the transiting body's longitude
  at that exact JD and confirming it matches the target within a small
  tolerance (mirrors the reference script's "Verified Moon lon" step).

Return all events sorted chronologically. Each event: ISO 8601 UTC
timestamp, ISO 8601 timestamp in the birth location's local timezone
(reuse the timezone found during natal computation), which transiting
body, which natal point (key + formatted sign/degree label), and the
verified transiting-body longitude at that moment.

### API endpoints
- `POST /api/natal-chart` — body: birth date/time/place (or lat/lon).
  Returns the natal chart (points, sign/degree labels, retrograde flags,
  resolved lat/lon, resolved timezone name).
- `POST /api/conjunctions` — body: birth info (same shape) + date range +
  transiting body selection. Returns the natal chart AND the sorted
  conjunction events list (so the frontend can render both in one call
  without a second round trip).
- Validate all inputs with Pydantic; return clear 4xx errors for bad
  dates, unresolvable place names, or a date range over 12 months.
- Enable CORS for local frontend dev (`http://localhost:5173` etc — read
  allowed origins from an env var with a sensible local-dev default).

### Local run
`cd backend && uv venv .venv && uv pip install -r requirements.txt`
`uvicorn app.main:app --reload --port 8000`
Add a `README.md` section covering this exactly. Also include a minimal
`template.yaml` (AWS SAM) stub wiring the FastAPI app through Mangum as a
Lambda function behind API Gateway, for future deploy — it does not need
to be deployed or tested now, just present and plausible.

### Tests
Add at least a few `pytest` tests: natal longitude calc against a known
fixture (e.g. reproduce the reference script's hardcoded chart from a
matching birth date/time/place, if derivable — otherwise just sanity
checks: longitudes in [0,360), correct sign boundaries, geocoding +
timezone resolution for a known city, and that the conjunction search
returns events whose verified longitude matches the natal target within
tolerance). Document how to run: `pytest`.

## Frontend — detailed requirements

Directory: `frontend/`

Vite + React (TypeScript). Single page, no routing needed.

### Form
- Name (optional, just for display on results, not sent to any DB).
- Birth date picker.
- Birth time input (with a note that exact time matters for house cusps
  and precision).
- Birth place: free-text input (city, country) sent to backend for
  geocoding. Also support optional manual lat/lon override (advanced/
  collapsed section) for users who don't trust geocoding.
- Date range: start month+year and end month+year pickers, defaulting to
  the current month → +1 month, enforced client-side to a max 12-month
  span with a clear validation message if exceeded.
- Transiting body checkboxes: Moon (default checked), Sun (default
  unchecked) — at least one must be checked.
- Submit button, loading state, error display (surface backend 4xx
  messages plainly).

### Results
- Show the resolved natal chart (table: point, sign/degree, retrograde
  flag) so the user can sanity-check their birth data was interpreted
  correctly (resolved place, lat/lon, timezone shown too).
- Show the conjunction events as a sorted table: local date/time (birth
  location tz), UTC date/time, transiting body, natal point, verified
  longitude label. Group visually by month for readability if the list
  is long.
- If a search yields zero events (only possible for Sun since Moon should
  always yield hits for any month), show a clear "no conjunctions found"
  state rather than a blank table.

### Config
Backend base URL via a Vite env var (`VITE_API_BASE_URL`, defaulting to
`http://localhost:8000`) — don't hardcode.

### Local run
`cd frontend && npm install && npm run dev` — document exactly in
`README.md`.

## Top-level README.md
One-page overview: what this is, architecture diagram in words (React ->
FastAPI/Lambda -> pyswisseph), how to run backend + frontend locally
together, where things live, and a "Future work" section noting: actual
Lambda deployment via the SAM template, additional aspect types beyond
conjunction (trine, square, etc.) as a natural extension, saving/sharing
charts (would need a DB — explicitly out of scope per current design).

## Non-goals (explicitly out of scope for this pass)
- No authentication, no user accounts, no persistence/database.
- No deployment execution (SAM template is scaffolding only, not deployed).
- No aspects other than conjunction.
- No chart wheel graphic — this is a data table.

## Definition of done
- `backend/`: FastAPI app runs locally via uvicorn, `/api/natal-chart` and
  `/api/conjunctions` both work against a real test request (curl or
  pytest), pytest suite passes.
- `frontend/`: `npm run dev` serves a working form; a manual end-to-end
  test (enter a birth date/time/place, pick a date range, submit) returns
  and renders real conjunction results from the running backend.
- Both `README.md`s are accurate and were actually followed to verify the
  above (don't just write instructions — run them).
