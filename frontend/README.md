# Frontend — Astrology Conjunction Finder

Vite + React + TypeScript single page. One form, one request, two tables.
No routing, no state library, no UI framework — plain CSS in
`src/index.css` (tokens and element defaults) and `src/App.css` (layout and
components).

## Run locally

The backend must be running first — see `../backend/README.md`:

```bash
cd backend && .venv/bin/uvicorn app.main:app --reload --port 8000
```

Then, in another terminal:

```bash
cd frontend
npm install
npm run dev
```

Open <http://localhost:5173>. That origin is already in the backend's default
CORS allowlist.

Other scripts: `npm run build` (typecheck via `tsc -b`, then bundle to `dist/`),
`npm run preview` (serve the built bundle), `npm run lint` (oxlint).

## Configuration

| Variable | Default | Purpose |
| --- | --- | --- |
| `VITE_API_BASE_URL` | `http://localhost:8000` | Backend base URL |

The default matches the documented uvicorn command, so local development needs
no `.env` at all. To point elsewhere, copy `.env.example` to `.env`. The value is
inlined at build time, so a change needs a dev-server restart or a rebuild.

## Layout

```
src/
  main.tsx                     React root
  App.tsx                      page shell, request state (loading/error/result)
  api.ts                       fetch wrapper + FastAPI error-shape flattening
  types.ts                     mirrors backend/app/schemas.py
  dates.ts                     month arithmetic + ISO timestamp formatting
  env.d.ts                     types VITE_API_BASE_URL
  components/
    BirthForm.tsx              the form and all client-side validation
    NatalChartTable.tsx        resolved location summary + 25 natal points
    EventsTable.tsx            conjunctions, grouped by month
  index.css                    design tokens, element defaults
  App.css                      layout and component styles
```

## Behaviour worth knowing

**One request per search.** `POST /api/conjunctions` returns the natal chart and
the events together, so submitting the form makes exactly one round trip.

**Timestamps are never re-interpreted.** The backend sends each event twice — in
UTC and in the birth location's timezone — with the offset in the string.
`formatIsoInOwnZone` reads the ISO string's own fields rather than constructing
a `Date`, because `Date` would shift everything into *the viewer's* timezone.
Someone in Tokyo looking up a Toronto birth chart sees Toronto times, which is
the point. The per-row offset (`+01:00`) is shown because it changes across a
DST transition inside the window.

**Validation happens twice, deliberately.** The form blocks an over-long range,
a reversed range, missing fields, out-of-range coordinates and an empty body
selection before it sends anything, and shows the month span live as you change
the pickers. The backend enforces the same rules independently; when it rejects
something, `api.ts` flattens the response — `{"detail": "..."}` for 400s,
`{"detail": [{loc, msg}, ...]}` for Pydantic 422s — into one sentence and the
page shows it verbatim rather than a generic failure message.

**Advanced coordinates.** The collapsed section lets you override geocoding with
exact decimal degrees. The place-name text is still sent, but the backend then
uses it only as a display label. The timezone is always derived from the
coordinates.

**Month grouping.** Events are grouped under a heading for their *local* month,
matching the first column. Because the search window is whole calendar months in
UTC, an event in the last hours of the window can appear under the next month
locally — that is genuinely when it happens where you were born.

**Zero results.** Only realistically possible with Sun-only searches (the Moon
crosses every natal point about once a month). That case renders an explanatory
empty state, not an empty table.

## Manual verification

Checked in a real browser against a live backend:

- Full submit with a geocoded place name → natal chart and 57 events over a
  two-month Moon+Sun window, every "verified" cell matching the natal position
  beside it.
- A 1815 London birth resolves to `Europe/London` at `-00:01:15` (LMT, before
  the 1847 switch to GMT); a 1970 London birth resolves to `+01:00` (British
  Standard Time, 1968–1971). Both come from `zoneinfo`, not a fixed offset.
- Manual lat/lon override → no geocoding, coordinates used verbatim.
- 14-month range → blocked client-side with the span named.
- Unresolvable place name → the backend's 400 message shown verbatim.
- No transiting body checked → blocked client-side.
- Sun-only July 2026 for a chart with no natal point in that arc → the
  "no conjunctions found" state.
- No console or page errors at 1280px or 390px wide; the events table scrolls
  inside its own container on narrow screens instead of breaking the page.
