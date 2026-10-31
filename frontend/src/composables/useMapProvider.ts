/**
 * Map provider seam. Activity and Home surfaces render GPS tracks through this
 * abstraction so the concrete mapping library (Leaflet, MapLibre, MapTiler, …)
 * can be swapped — or omitted entirely on minimal builds — without touching any
 * view. Self-hosted instances run the default no-op until a provider is
 * registered during bootstrap.
 *
 * This module intentionally ships no mapping dependency; it defines only the
 * contract and registration seam.
 */
import { createProviderSeam } from '@/composables/createProviderSeam'

/** A single geographic coordinate in decimal degrees. */
export interface GeoPoint {
  /** Latitude in decimal degrees. */
  lat: number
  /** Longitude in decimal degrees. */
  lng: number
}

/** A polyline track plus optional start/finish emphasis markers. */
export interface MapTrack {
  /** Ordered coordinates forming the route polyline. */
  points: GeoPoint[]
  /** Optional start point, emphasised with a distinct (green) marker. */
  start?: GeoPoint
  /** Optional finish point, emphasised with a distinct (red) marker. */
  finish?: GeoPoint
}

/** Options controlling a single map render. */
export interface MapRenderOptions {
  /** The track to display. */
  track: MapTrack
  /** Whether the map responds to pan/zoom. Defaults to provider preference. */
  interactive?: boolean
}

/** Called with a fraction along the route, or `null` when the pointer leaves it. */
export type TrackHoverHandler = (fraction: number | null) => void

/** Imperative handle to a mounted map, returned by {@link MapProvider.mount}. */
export interface MapInstance {
  /** Re-renders the map with new options (e.g. after data refresh). */
  update(options: MapRenderOptions): void
  /** Re-fits the viewport to the current track (e.g. after the user panned). */
  recenter(): void
  /** Moves the route cursor. `null` removes it. Does not refit the map. */
  setCursor(point: GeoPoint | null): void
  /** Receives hover along the route line. `null` stops listening. */
  setTrackHover(handler: TrackHoverHandler | null): void
  /** Tears down the map and releases resources. */
  destroy(): void
}

/**
 * Pluggable map renderer.
 *
 * @property name - Stable identifier of the concrete implementation.
 * @property mount - Mounts a map into `target` and returns its handle.
 */
export interface MapProvider {
  readonly name: string
  mount(target: HTMLElement, options: MapRenderOptions): MapInstance
}

/**
 * Default provider used until a real one is registered. It renders nothing and
 * reports as unavailable so consumers can show a fallback surface instead.
 */
const noopMapProvider: MapProvider = {
  name: 'noop',
  mount() {
    return {
      update() {},
      recenter() {},
      setCursor() {},
      setTrackHover() {},
      destroy() {},
    }
  },
}

const seam = createProviderSeam<MapProvider>(noopMapProvider)

/**
 * Registers the active map provider. Call once during bootstrap on deployments
 * that bundle a mapping library.
 *
 * @param next - The provider to install.
 */
export function setMapProvider(next: MapProvider): void {
  seam.set(next)
}

/** Result of {@link useMapProvider}. */
export interface UseMapProvider {
  /** The active provider (the no-op when none is registered). */
  provider: MapProvider
  /** `true` when a real provider has been registered. */
  isAvailable: boolean
}

/**
 * Map provider hook.
 *
 * @returns The active provider plus an availability flag for fallback UI.
 */
export function useMapProvider(): UseMapProvider {
  return {
    provider: seam.get(),
    isAvailable: seam.isRegistered(),
  }
}
