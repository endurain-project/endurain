/**
 * Concrete Chart.js implementation of the {@link ChartProvider} seam. Registered
 * during bootstrap so Activity and Home surfaces can render metric charts. Kept
 * behind the seam so minimal builds can omit Chart.js entirely.
 *
 * The pure {@link buildChartConfiguration} helper is exported so the seam →
 * Chart.js translation can be unit-tested without a canvas.
 */
import { Chart, registerables, type ChartConfiguration, type ChartDataset } from 'chart.js'
import zoomPlugin from 'chartjs-plugin-zoom'

import type {
  ChartInstance,
  ChartProvider,
  ChartRenderOptions,
} from '@/composables/useChartProvider'

Chart.register(...registerables, zoomPlugin)

/** Design-token-aligned series palette, brand teal first. */
export const DEFAULT_CHART_PALETTE: readonly string[] = [
  '#1d9e75',
  '#2563eb',
  '#f59e0b',
  '#ef4444',
  '#8b5cf6',
  '#14b8a6',
]

/** Configuration for the Chart.js provider. */
export interface ChartJsChartProviderConfig {
  /** Colour palette used for series without an explicit colour. */
  palette?: readonly string[]
}

/**
 * Picks a deterministic colour for a series, honouring an explicit colour when
 * provided and otherwise cycling the palette.
 *
 * @param index - Zero-based series index.
 * @param explicit - The series' own colour, if any.
 * @param palette - Palette to cycle when no explicit colour is set.
 * @returns A concrete colour string.
 */
function colorFor(index: number, explicit: string | undefined, palette: readonly string[]): string {
  if (explicit) {
    return explicit
  }
  // The literal fallback guards the (impossible in practice) empty-palette case
  // so the return type stays a non-nullable string under noUncheckedIndexedAccess.
  return palette[index % palette.length] ?? DEFAULT_CHART_PALETTE[0] ?? '#1d9e75'
}

/** Converts a 6-digit hex colour to an `rgba()` string at the given alpha. */
function hexToRgba(hex: string, alpha: number): string {
  const normalized = hex.replace('#', '')
  const r = Number.parseInt(normalized.slice(0, 2), 16)
  const g = Number.parseInt(normalized.slice(2, 4), 16)
  const b = Number.parseInt(normalized.slice(4, 6), 16)
  return `rgba(${r}, ${g}, ${b}, ${alpha})`
}

/**
 * Opacity of the flat fill under line/area charts. A calm translucent tint
 * rather than a gradient, per the design system's "flat fills with opacity"
 * rule.
 */
const AREA_FILL_ALPHA = 0.15

/**
 * Translates seam {@link ChartRenderOptions} into a Chart.js configuration.
 * Pure and deterministic so it can be unit-tested without a canvas.
 *
 * @param options - The chart to render.
 * @param palette - Optional colour palette for series without explicit colours.
 * @returns A Chart.js configuration object.
 */
export function buildChartConfiguration(
  options: ChartRenderOptions,
  palette: readonly string[] = DEFAULT_CHART_PALETTE,
): ChartConfiguration<'line' | 'bar'> {
  const type: 'line' | 'bar' = options.kind === 'bar' ? 'bar' : 'line'

  // A linear x-axis needs `{x, y}` points; a category axis takes bare y-values
  // aligned to `labels`. `toPoints` bridges a series' y-values to whichever the
  // active axis expects.
  const xValues = options.xValues
  const toPoints = (data: number[]): number[] | { x: number; y: number }[] =>
    xValues ? data.map((y, i) => ({ x: xValues[i] ?? i, y })) : data

  // Exact data extremes for the linear x-axis so it ends precisely at the last
  // sample (e.g. 12.51 km, 48:00) instead of Chart.js padding out to the next
  // round tick. Computed with a loop, not `Math.max(...xValues)`, since a spread
  // over thousands of samples can overflow the call stack.
  let xMin: number | undefined
  let xMax: number | undefined
  if (xValues && xValues.length > 0) {
    xMin = xValues[0]
    xMax = xValues[0]
    for (const v of xValues) {
      if (v < (xMin as number)) xMin = v
      if (v > (xMax as number)) xMax = v
    }
  }

  const datasets: ChartDataset<'line' | 'bar'>[] = options.series.map((series, index) => {
    const color = colorFor(index, series.color, palette)
    // A dashed series is a reference/target line: render it as a dashed line
    // overlay regardless of the chart's geometry, so it sits on top of bars as a
    // mixed bar/line chart — mirroring v1's dashed target lines.
    if (series.dashed) {
      return {
        type: 'line',
        label: series.label,
        data: toPoints(series.data),
        borderColor: color,
        backgroundColor: color,
        borderWidth: 2,
        borderDash: [6, 6],
        fill: false,
        tension: 0,
        pointRadius: 0,
      }
    }
    // Line/area charts get a flat translucent fill below the line (a calm tint,
    // not a gradient — per the design system); bars stay solid.
    const filled = type === 'line'
    return {
      label: series.label,
      data: toPoints(series.data),
      borderColor: color,
      backgroundColor: filled ? hexToRgba(color, AREA_FILL_ALPHA) : color,
      borderWidth: 2,
      fill: filled,
      tension: 0.3,
      pointRadius: 0,
    }
  })

  return {
    type,
    data: {
      labels: options.labels ?? [],
      datasets,
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      animation: false,
      plugins: {
        legend: { display: options.series.length > 1 },
        tooltip: {
          callbacks: {
            // X value (tooltip title): on a linear axis format the raw x
            // (e.g. `2 km`, `1:23:45`); on a category axis append the unit to the
            // label (e.g. `0.7 km`). Distance-less category charts pass no unit.
            title: (items) => {
              const item = items[0]
              if (!item) {
                return ''
              }
              if (options.xFormat) {
                return options.xFormat(Number(item.parsed.x))
              }
              const raw = item.label ?? ''
              return options.xUnit && raw ? `${raw} ${options.xUnit}` : raw
            },
            // Y value: `<series>: <formatted>` using the domain formatter.
            label: (ctx) => {
              const y = ctx.parsed.y
              if (y === null || y === undefined) {
                return ctx.dataset.label ?? ''
              }
              const formatted = options.valueFormat?.(y) ?? String(y)
              return ctx.dataset.label ? `${ctx.dataset.label}: ${formatted}` : formatted
            },
          },
        },
        // Interactive pan/zoom along the distance axis; wheel + drag on
        // desktop, pinch on touch (the v2 plugin handles pinch natively).
        zoom: options.zoom
          ? {
              zoom: {
                wheel: { enabled: true },
                pinch: { enabled: true },
                mode: 'x',
              },
              pan: { enabled: true, mode: 'x' },
            }
          : undefined,
      },
      scales: {
        // Linear axis (proportional ticks + title) when numeric x-values are
        // supplied; otherwise a plain category axis over `labels`.
        x: xValues
          ? {
              type: 'linear',
              display: true,
              // Clamp the axis to the actual data range so it ends exactly at
              // the last sample (e.g. 12.51 km, 48:00). Chart.js otherwise pads
              // out to the next round tick (14 km, 50:00); `bounds: 'data'` alone
              // is not enough in v4, so pin min/max to the data extremes too.
              bounds: 'data',
              min: xMin,
              max: xMax,
              title: options.xLabel ? { display: true, text: options.xLabel } : undefined,
              ticks: options.xFormat
                ? { callback: (value) => options.xFormat?.(Number(value)) ?? String(value) }
                : {},
            }
          : { display: true },
        y: {
          display: true,
          reverse: options.invertY ?? false,
          ticks: options.valueFormat
            ? { callback: (value) => options.valueFormat?.(Number(value)) ?? String(value) }
            : {},
        },
      },
    },
  }
}

/**
 * Creates a Chart.js-backed chart provider.
 *
 * @param config - Optional palette override.
 * @returns A {@link ChartProvider} ready to register via `setChartProvider`.
 */
export function createChartJsChartProvider(config: ChartJsChartProviderConfig = {}): ChartProvider {
  const palette = config.palette ?? DEFAULT_CHART_PALETTE

  return {
    name: 'chartjs',
    mount(target: HTMLElement, options: ChartRenderOptions): ChartInstance {
      const canvas = document.createElement('canvas')
      target.replaceChildren(canvas)

      let chart = new Chart(canvas, buildChartConfiguration(options, palette))

      return {
        // Recreate the chart on every update rather than patching in place.
        // Updates fire only on real changes (x-axis basis toggle, data load,
        // locale) — never per frame — so the cost is negligible, and a fresh
        // chart guarantees the scale title, tick/tooltip formatters, geometry
        // and the zoom plugin's cached x-range all track the new options.
        // Patching only `data` left the axis title/labels stale and the old
        // basis's x-range zoomed in (the graph ran off-screen after toggling).
        update(next: ChartRenderOptions): void {
          chart.destroy()
          chart = new Chart(canvas, buildChartConfiguration(next, palette))
        },
        destroy(): void {
          chart.destroy()
        },
      }
    },
  }
}
