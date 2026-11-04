import type { ActivityStream, HrZoneBucket } from '../types'
import { STREAM_TYPE } from '../types'
import { themeColor } from '@/lib/themeColor'

/**
 * Resolves the colour for a heart-rate zone on the five-zone ramp
 * (blue → green → amber → orange → red), read from the design tokens.
 *
 * @param zone - Zone number, 1–5.
 * @returns The zone's colour (defaults to the top zone colour out of range).
 */
export function hrZoneColor(zone: number): string {
  switch (zone) {
    case 1:
      return themeColor('--color-info')
    case 2:
      return themeColor('--color-goal')
    case 3:
      return themeColor('--color-effort')
    case 4:
      return themeColor('--color-hr-zone-4')
    default:
      return themeColor('--color-hr')
  }
}

/**
 * Extracts the decoded HR zone buckets from the HR stream, when present.
 *
 * @param streams - The activity's metric streams.
 * @returns The HR zone buckets, or `null` when no HR zones are available.
 */
export function extractHrZones(streams: ActivityStream[]): HrZoneBucket[] | null {
  const hrStream = streams.find((stream) => stream.streamType === STREAM_TYPE.hr)
  return hrStream?.hrZones ?? null
}
