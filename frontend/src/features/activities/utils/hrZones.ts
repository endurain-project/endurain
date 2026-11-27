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
