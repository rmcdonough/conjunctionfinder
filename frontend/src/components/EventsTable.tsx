import { formatIsoInOwnZone, isoMonthLabel, isoOffsetLabel } from '../dates'
import type { ConjunctionEvent, ConjunctionsResponse } from '../types'

const BODY_GLYPH: Record<ConjunctionEvent['transiting_body'], string> = {
  moon: '☾',
  sun: '☉',
}

const BODY_NAME: Record<ConjunctionEvent['transiting_body'], string> = {
  moon: 'Moon',
  sun: 'Sun',
}

/**
 * Group events under a month heading, keyed by their LOCAL month.
 *
 * Events arrive sorted, and grouping by local month keeps the headings
 * consistent with the local timestamp in the first column. A conjunction late
 * on the last day of a month in UTC can therefore appear under the previous
 * month — that is genuinely when it happened where you were born.
 */
function groupByLocalMonth(
  events: ConjunctionEvent[],
): { month: string; events: ConjunctionEvent[] }[] {
  const groups: { month: string; events: ConjunctionEvent[] }[] = []
  for (const event of events) {
    const month = isoMonthLabel(event.local)
    const last = groups[groups.length - 1]
    if (last && last.month === month) last.events.push(event)
    else groups.push({ month, events: [event] })
  }
  return groups
}

function formatRange(startIso: string, endIso: string): string {
  return `${isoMonthLabel(`${startIso}T00:00:00`)} – ${isoMonthLabel(`${endIso}T00:00:00`)}`
}

export function EventsTable({ result }: { result: ConjunctionsResponse }) {
  const { events, natal_chart: chart, bodies } = result
  const bodyNames = bodies.map((b) => BODY_NAME[b]).join(' and ')
  const groups = groupByLocalMonth(events)

  if (events.length === 0) {
    return (
      <section className="card">
        <h2>Conjunctions</h2>
        <p className="empty">
          No {bodyNames} conjunctions found between{' '}
          {formatRange(result.range_start, result.range_end)}.
        </p>
        <p className="hint">
          The Sun only meets each natal point once a year, so a short window can
          genuinely come up empty. Widen the range, or add the Moon — it crosses
          every natal point about once a month.
        </p>
      </section>
    )
  }

  return (
    <section className="card">
      <h2>
        Conjunctions{' '}
        <span className="count">
          {events.length} event{events.length === 1 ? '' : 's'}
        </span>
      </h2>
      <p className="hint">
        Transiting {bodyNames} over natal points,{' '}
        {formatRange(result.range_start, result.range_end)}. Local times are in{' '}
        {chart.timezone}, the birth location&rsquo;s timezone.
      </p>

      <div className="table-scroll">
        <table>
          <thead>
            <tr>
              <th scope="col">Local ({chart.timezone})</th>
              <th scope="col">UTC</th>
              <th scope="col">Transiting</th>
              <th scope="col">Natal point</th>
              <th scope="col">Natal position</th>
              <th scope="col">Verified</th>
            </tr>
          </thead>
          {groups.map((group) => (
            <tbody key={group.month}>
              <tr className="month-heading">
                <th scope="colgroup" colSpan={6}>
                  {group.month}
                  <span className="count">
                    {group.events.length} event
                    {group.events.length === 1 ? '' : 's'}
                  </span>
                </th>
              </tr>
              {group.events.map((event) => (
                <tr key={`${event.transiting_body}-${event.natal_key}-${event.utc}`}>
                  <td className="mono">
                    {formatIsoInOwnZone(event.local)}{' '}
                    <span className="muted">
                      {isoOffsetLabel(event.local, { short: true })}
                    </span>
                  </td>
                  <td className="mono muted">
                    {formatIsoInOwnZone(event.utc, { weekday: false })}
                  </td>
                  <td>
                    <span className="glyph" aria-hidden="true">
                      {BODY_GLYPH[event.transiting_body]}
                    </span>{' '}
                    {BODY_NAME[event.transiting_body]}
                  </td>
                  <th scope="row">{event.natal_key}</th>
                  <td className="mono">{event.natal_label}</td>
                  <td className="mono muted">{event.transiting_label}</td>
                </tr>
              ))}
            </tbody>
          ))}
        </table>
      </div>
      <p className="hint">
        Every crossing is re-checked by recomputing the transiting body&rsquo;s
        longitude at that exact instant. The &ldquo;verified&rdquo; column is
        that recomputed value, so it should match the natal position beside it.
      </p>
    </section>
  )
}
