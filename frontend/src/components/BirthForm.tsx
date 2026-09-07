import { useState } from 'react'
import {
  MONTH_NAMES,
  addMonths,
  currentMonthYear,
  monthIndex,
  monthSpan,
  type MonthYear,
} from '../dates'
import type { ConjunctionsRequest, TransitingBody } from '../types'

const MAX_RANGE_MONTHS = 12

export interface BirthFormProps {
  loading: boolean
  onSubmit: (request: ConjunctionsRequest, displayName: string) => void
}

const YEAR_MIN = 1800
const YEAR_MAX = 2399

function MonthYearPicker({
  legend,
  value,
  onChange,
  idPrefix,
}: {
  legend: string
  value: MonthYear
  onChange: (next: MonthYear) => void
  idPrefix: string
}) {
  return (
    <div className="month-year">
      <span className="month-year-legend">{legend}</span>
      <div className="month-year-inputs">
        <select
          id={`${idPrefix}-month`}
          aria-label={`${legend} month`}
          value={value.month}
          onChange={(e) => onChange({ ...value, month: Number(e.target.value) })}
        >
          {MONTH_NAMES.map((name, i) => (
            <option key={name} value={i + 1}>
              {name}
            </option>
          ))}
        </select>
        <input
          id={`${idPrefix}-year`}
          aria-label={`${legend} year`}
          type="number"
          min={YEAR_MIN}
          max={YEAR_MAX}
          step={1}
          value={value.year}
          onChange={(e) => onChange({ ...value, year: Number(e.target.value) })}
        />
      </div>
    </div>
  )
}

export function BirthForm({ loading, onSubmit }: BirthFormProps) {
  const thisMonth = currentMonthYear()

  const [name, setName] = useState('')
  const [birthDate, setBirthDate] = useState('')
  const [birthTime, setBirthTime] = useState('12:00')
  const [birthPlace, setBirthPlace] = useState('')

  const [showAdvanced, setShowAdvanced] = useState(false)
  const [useManualCoords, setUseManualCoords] = useState(false)
  const [latitude, setLatitude] = useState('')
  const [longitude, setLongitude] = useState('')

  const [start, setStart] = useState<MonthYear>(thisMonth)
  const [end, setEnd] = useState<MonthYear>(addMonths(thisMonth, 1))

  const [bodies, setBodies] = useState<Record<TransitingBody, boolean>>({
    moon: true,
    sun: false,
  })

  const [validationError, setValidationError] = useState<string | null>(null)

  const span = monthSpan(start, end)
  const selectedBodies = (['moon', 'sun'] as TransitingBody[]).filter(
    (b) => bodies[b],
  )

  // Live hints, shown as you type rather than only on submit.
  const rangeHint =
    monthIndex(end) < monthIndex(start)
      ? 'End month must not be before start month.'
      : span > MAX_RANGE_MONTHS
        ? `That range spans ${span} months. The maximum is ${MAX_RANGE_MONTHS}.`
        : null

  function toggleBody(body: TransitingBody) {
    setBodies((prev) => ({ ...prev, [body]: !prev[body] }))
  }

  function validate(): string | null {
    if (!birthDate) return 'Enter a birth date.'
    if (!birthTime) return 'Enter a birth time.'

    if (useManualCoords) {
      const lat = Number(latitude)
      const lon = Number(longitude)
      if (latitude.trim() === '' || longitude.trim() === '') {
        return 'Enter both a latitude and a longitude, or switch off the manual override.'
      }
      if (!Number.isFinite(lat) || lat < -90 || lat > 90) {
        return 'Latitude must be a number between -90 and 90.'
      }
      if (!Number.isFinite(lon) || lon < -180 || lon > 180) {
        return 'Longitude must be a number between -180 and 180.'
      }
    } else if (!birthPlace.trim()) {
      return 'Enter a birth place, or use the manual latitude/longitude override.'
    }

    for (const { label, value } of [
      { label: 'Start', value: start },
      { label: 'End', value: end },
    ]) {
      if (
        !Number.isInteger(value.year) ||
        value.year < YEAR_MIN ||
        value.year > YEAR_MAX
      ) {
        return `${label} year must be between ${YEAR_MIN} and ${YEAR_MAX}.`
      }
    }

    if (rangeHint) return rangeHint
    if (selectedBodies.length === 0) {
      return 'Select at least one transiting body (Moon and/or Sun).'
    }
    return null
  }

  function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const problem = validate()
    setValidationError(problem)
    if (problem) return

    const request: ConjunctionsRequest = {
      birth_date: birthDate,
      birth_time: birthTime,
      // Always send the place text when present: with manual coordinates the
      // backend uses it only as a display label, and skips geocoding.
      birth_place: birthPlace.trim() || null,
      latitude: useManualCoords ? Number(latitude) : null,
      longitude: useManualCoords ? Number(longitude) : null,
      name: name.trim() || null,
      start_year: start.year,
      start_month: start.month,
      end_year: end.year,
      end_month: end.month,
      bodies: selectedBodies,
    }
    onSubmit(request, name.trim())
  }

  return (
    <form className="card form" onSubmit={handleSubmit} noValidate>
      <fieldset disabled={loading}>
        <legend>Birth details</legend>

        <div className="field">
          <label htmlFor="name">Name (optional)</label>
          <input
            id="name"
            type="text"
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="Shown on your results only"
            autoComplete="off"
          />
          <p className="hint">Never stored — this app has no database.</p>
        </div>

        <div className="field-row">
          <div className="field">
            <label htmlFor="birth-date">Birth date</label>
            <input
              id="birth-date"
              type="date"
              value={birthDate}
              onChange={(e) => setBirthDate(e.target.value)}
              min="1800-01-01"
              max="2399-12-31"
              required
            />
          </div>

          <div className="field">
            <label htmlFor="birth-time">Birth time (24h, local)</label>
            <input
              id="birth-time"
              type="time"
              value={birthTime}
              onChange={(e) => setBirthTime(e.target.value)}
              required
            />
          </div>
        </div>

        <p className="hint">
          The exact time matters: house cusps move roughly a degree every four
          minutes, and the Moon moves about half a degree an hour. A guessed time
          gives you a roughly right chart with definitely wrong cusps.
        </p>

        <div className="field">
          <label htmlFor="birth-place">Birth place</label>
          <input
            id="birth-place"
            type="text"
            value={birthPlace}
            onChange={(e) => setBirthPlace(e.target.value)}
            placeholder="Toronto, Ontario, Canada"
            autoComplete="off"
          />
          <p className="hint">
            Geocoded on the server. City plus country works best; the resolved
            place, coordinates and timezone are shown with your results so you
            can check them.
          </p>
        </div>

        <div className="advanced">
          <button
            type="button"
            className="disclosure"
            aria-expanded={showAdvanced}
            onClick={() => setShowAdvanced((v) => !v)}
          >
            {showAdvanced ? '▾' : '▸'} Advanced: exact coordinates
          </button>

          {showAdvanced && (
            <div className="advanced-body">
              <label className="checkbox">
                <input
                  type="checkbox"
                  checked={useManualCoords}
                  onChange={(e) => setUseManualCoords(e.target.checked)}
                />
                Use these coordinates instead of geocoding the place name
              </label>

              <div className="field-row">
                <div className="field">
                  <label htmlFor="latitude">Latitude</label>
                  <input
                    id="latitude"
                    type="number"
                    step="any"
                    min={-90}
                    max={90}
                    value={latitude}
                    onChange={(e) => setLatitude(e.target.value)}
                    placeholder="43.6532"
                    disabled={!useManualCoords}
                  />
                </div>
                <div className="field">
                  <label htmlFor="longitude">Longitude</label>
                  <input
                    id="longitude"
                    type="number"
                    step="any"
                    min={-180}
                    max={180}
                    value={longitude}
                    onChange={(e) => setLongitude(e.target.value)}
                    placeholder="-79.3832"
                    disabled={!useManualCoords}
                  />
                </div>
              </div>
              <p className="hint">
                Decimal degrees, north and east positive. The timezone is still
                derived from the coordinates.
              </p>
            </div>
          )}
        </div>
      </fieldset>

      <fieldset disabled={loading}>
        <legend>Search window</legend>

        <div className="field-row">
          <MonthYearPicker
            legend="From"
            idPrefix="start"
            value={start}
            onChange={setStart}
          />
          <MonthYearPicker
            legend="To"
            idPrefix="end"
            value={end}
            onChange={setEnd}
          />
        </div>

        <p className={rangeHint ? 'hint hint-warn' : 'hint'}>
          {rangeHint ??
            `${span} month${span === 1 ? '' : 's'}, inclusive. Maximum ${MAX_RANGE_MONTHS}.`}
        </p>

        <div className="field">
          <span className="label-like">Transiting bodies</span>
          <label className="checkbox">
            <input
              type="checkbox"
              checked={bodies.moon}
              onChange={() => toggleBody('moon')}
            />
            Moon — conjuncts every natal point about once a month
          </label>
          <label className="checkbox">
            <input
              type="checkbox"
              checked={bodies.sun}
              onChange={() => toggleBody('sun')}
            />
            Sun — conjuncts each natal point once a year
          </label>
          {selectedBodies.length === 0 && (
            <p className="hint hint-warn">Select at least one.</p>
          )}
        </div>
      </fieldset>

      {validationError && (
        <p className="error" role="alert">
          {validationError}
        </p>
      )}

      <button type="submit" className="submit" disabled={loading}>
        {loading ? 'Searching…' : 'Find conjunctions'}
      </button>
    </form>
  )
}
