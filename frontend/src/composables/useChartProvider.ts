/**
 * Chart provider seam. Activity and Home surfaces render metric charts through
 * this abstraction so the concrete charting library (Chart.js, unovis, ECharts,
 * …) can be swapped — or omitted on minimal builds — without touching any view.
 * Self-hosted instances run the default no-op until a provider is registered
 * during bootstrap.
 *
 * This module intentionally ships no charting dependency; it defines only the
 * contract and registration seam.
 */
import { createProviderSeam } from '@/composables/createProviderSeam'

/** Supported chart geometries. */
export type ChartKind = 'line' | 'area' | 'bar'

/** A single named data series. */
export interface ChartSeries {
  /** Series label shown in legends/tooltips. */
  label: string
  /** Numeric values aligned to {@link ChartRenderOptions.labels}. */
  data: number[]
  /** Optional explicit colour; providers may fall back to a palette. */
  color?: string
  /**
   * Renders the series as a dashed reference line — e.g. a target/goal — drawn
   * as a line overlay even on bar charts (a mixed bar/line chart). Providers
   * without dashed support fall back to a solid line.
   */
  dashed?: boolean
}

/** Options controlling a single chart render. */
export interface ChartRenderOptions {
  /** Chart geometry. */
  kind: ChartKind
  /** One or more series to plot. */
  series: ChartSeries[]
  /** X-axis category labels aligned to each series' values. */
  labels?: string[]
  /**
   * Optional numeric x-values aligned to each series' values. When present the
   * provider renders a proportional **linear** x-axis (Chart.js picks round
   * ticks) instead of a category axis, and {@link labels} is ignored. Used for
   * distance (km/mi) and elapsed-time axes so ticks reflect true spacing.
   */
  xValues?: number[]
  /**
   * Optional x-axis title (e.g. `Distance (km)`, `Time`). Rendered as the scale
   * title when {@link xValues} drives a linear axis.
   */
  xLabel?: string
  /**
   * Optional formatter for linear x-axis ticks and the tooltip's x value (e.g.
   * `2 km`, `1:23:45`). Receives the raw numeric x. Used only with
   * {@link xValues}.
   */
  xFormat?: (value: number) => string
  /**
   * Optional unit suffix for x-axis values (e.g. `km`, `mi`). Appended to the
   * tooltip's x value so a hover reads `0.7 km` rather than a bare `0.7`; axis
   * ticks stay unitless to avoid clutter. Empty/omitted for self-describing
   * axes such as time.
   */
  xUnit?: string
  /**
   * Optional formatter applied to y-axis ticks and tooltip values. Lets a
   * fitness surface render domain units (pace `M:SS`, `bpm`, `W`) without the
   * view knowing the charting library. Receives the raw numeric value.
   */
  valueFormat?: (value: number) => string
  /**
   * Inverts the y-axis so smaller values sit at the top. Used for pace charts
   * where a lower (faster) pace is "better".
   */
  invertY?: boolean
  /**
   * Enables interactive pan/zoom along the x-axis (wheel + drag on desktop,
   * pinch on touch). Providers without zoom support ignore this.
   */
  zoom?: boolean
}

/** Imperative handle to a mounted chart, returned by {@link ChartProvider.mount}. */
export interface ChartInstance {
  /** Re-renders the chart with new options (e.g. after data refresh). */
  update(options: ChartRenderOptions): void
  /** Tears down the chart and releases resources. */
  destroy(): void
}

/**
 * Pluggable chart renderer.
 *
 * @property name - Stable identifier of the concrete implementation.
 * @property mount - Mounts a chart into `target` and returns its handle.
 */
export interface ChartProvider {
  readonly name: string
  mount(target: HTMLElement, options: ChartRenderOptions): ChartInstance
}

/**
 * Default provider used until a real one is registered. It renders nothing and
 * reports as unavailable so consumers can show a fallback surface instead.
 */
const noopChartProvider: ChartProvider = {
  name: 'noop',
  mount() {
    return {
      update() {},
      destroy() {},
    }
  },
}

const seam = createProviderSeam<ChartProvider>(noopChartProvider)

/**
 * Registers the active chart provider. Call once during bootstrap on
 * deployments that bundle a charting library.
 *
 * @param next - The provider to install.
 */
export function setChartProvider(next: ChartProvider): void {
  seam.set(next)
}

/** Result of {@link useChartProvider}. */
export interface UseChartProvider {
  /** The active provider (the no-op when none is registered). */
  provider: ChartProvider
  /** `true` when a real provider has been registered. */
  isAvailable: boolean
}

/**
 * Chart provider hook.
 *
 * @returns The active provider plus an availability flag for fallback UI.
 */
export function useChartProvider(): UseChartProvider {
  return {
    provider: seam.get(),
    isAvailable: seam.isRegistered(),
  }
}
