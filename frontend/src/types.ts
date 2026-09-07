/** Mirrors the Pydantic models in backend/app/schemas.py. */

export type TransitingBody = 'moon' | 'sun'

export type NatalPointCategory = 'luminary' | 'planet' | 'node' | 'house'

export interface NatalPoint {
  key: string
  category: NatalPointCategory
  longitude: number
  sign: string
  degree_in_sign: number
  /** e.g. "25°16′00″ Leo" */
  label: string
  retrograde: boolean
  /** Longitude speed in °/day; null for house cusps. */
  speed: number | null
}

export interface NatalChart {
  name: string | null
  points: NatalPoint[]
  latitude: number
  longitude: number
  resolved_place: string
  /** IANA timezone of the birth place, e.g. "America/Toronto". */
  timezone: string
  birth_datetime_local: string
  birth_datetime_utc: string
  julian_day: number
}

export interface ConjunctionEvent {
  utc: string
  local: string
  julian_day: number
  transiting_body: TransitingBody
  natal_key: string
  natal_label: string
  natal_longitude: number
  transiting_longitude: number
  transiting_label: string
}

export interface ConjunctionsResponse {
  natal_chart: NatalChart
  events: ConjunctionEvent[]
  event_count: number
  range_start: string
  range_end: string
  bodies: TransitingBody[]
}

export interface ConjunctionsRequest {
  birth_date: string
  birth_time: string
  birth_place?: string | null
  latitude?: number | null
  longitude?: number | null
  name?: string | null
  start_year: number
  start_month: number
  end_year: number
  end_month: number
  bodies: TransitingBody[]
}
