import type { MapConfig } from '@/features/config/types'

/** Default OpenStreetMap configuration used when server settings are unavailable. */
export const DEFAULT_MAP_CONFIG: Readonly<MapConfig> = Object.freeze({
  tileUrl: 'https://tile.openstreetmap.org/{z}/{x}/{y}.png',
  attribution:
    '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
})
