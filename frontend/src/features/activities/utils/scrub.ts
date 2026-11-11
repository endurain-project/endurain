import type { GeoPoint } from '@/composables/useMapProvider'

/**
 * Sample index for a position along a series. `0` is the first sample and `1`
 * is the last. Charts share this fraction because each x-axis spreads its own
 * samples evenly across the activity.
 *
 * @param length - Number of samples.
 * @param fraction - Position from 0 to 1.
 * @returns A clamped index.
 */
export function indexAtFraction(length: number, fraction: number): number {
  if (length <= 1) {
    return 0
  }
  const clamped = Math.min(1, Math.max(0, fraction))
  return Math.round(clamped * (length - 1))
}

/**
 * GPS point at the same fraction the charts use.
 *
 * @param points - Ordered route points.
 * @param fraction - Position from 0 to 1.
 * @returns The point, or `null` when the route is empty.
 */
export function pointAtFraction(points: readonly GeoPoint[], fraction: number): GeoPoint | null {
  return points[indexAtFraction(points.length, fraction)] ?? null
}

/**
 * Index of the route point closest to a map coordinate.
 *
 * Compares squared degrees. A walk or ride is small enough that this matches
 * the nearest vertex without a geodesic calculation on every move.
 *
 * @param points - Ordered route points.
 * @param lat - Latitude under the pointer.
 * @param lng - Longitude under the pointer.
 * @returns The closest index, or 0 when the route is empty.
 */
export function nearestTrackIndex(points: readonly GeoPoint[], lat: number, lng: number): number {
  let best = 0
  let bestDistance = Infinity
  for (let index = 0; index < points.length; index += 1) {
    const point = points[index]
    if (!point) {
      continue
    }
    const dLat = point.lat - lat
    const dLng = point.lng - lng
    const distance = dLat * dLat + dLng * dLng
    if (distance < bestDistance) {
      bestDistance = distance
      best = index
    }
  }
  return best
}
