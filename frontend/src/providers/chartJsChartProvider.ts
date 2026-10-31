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
  ChartCursorGeometry,
  ChartInstance,
  ChartProvider,
  ChartRenderOptions,
} from '@/composables/useChartProvider'
import { indexAtFraction } from '@/features/activities/utils/scrub'
import { themeColor } from '@/lib/themeColor'

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

  const datasets: ChartDataset<'line' | 'bar'>[] = options.series.map((series, index) => {
    const color = colorFor(index, series.color, palette)
    // A dashed series is a reference/target line: render it as a dashed line
    // overlay regardless of the chart's geometry, so it sits on top of bars as a
    // mixed bar/line chart — mirroring v1's dashed target lines.
    if (series.dashed) {
      return {
        type: 'line',
        label: series.label,
        data: series.data,
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
      data: series.data,
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
      // The shared cursor is an HTML overlay. Skip Chart.js hover work on
      // activity charts so a pointer move does not rebuild a tooltip. Health
      // charts omit this and keep the default hover events.
      ...(options.showTooltip === false ? { events: [] } : {}),
      plugins: {
        legend: { display: options.series.length > 1 },
        tooltip:
          options.showTooltip === false
            ? { enabled: false }
            : {
                // The Chart.js default is a black box. Follow the popover, including dark mode.
                backgroundColor: themeColor('--color-popover'),
                titleColor: themeColor('--color-popover-foreground'),
                bodyColor: themeColor('--color-popover-foreground'),
                borderColor: themeColor('--color-border'),
                borderWidth: 1,
                padding: 8,
                cornerRadius: 8,
                displayColors: false,
                callbacks: {
                  // X value (tooltip title): append the axis unit (e.g. `0.7 km`) so a
                  // hover is self-describing. Distance-less charts pass no unit.
                  title: (items) => {
                    const raw = items[0]?.label ?? ''
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
        x: { display: true },
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

      const initialConfig = buildChartConfiguration(options, palette)
      let currentType = initialConfig.type
      let chart = new Chart(canvas, initialConfig)

      /** Number of x samples currently drawn. */
      const sampleCount = (): number => {
        const labels = chart.data.labels
        if (Array.isArray(labels) && labels.length > 0) {
          return labels.length
        }
        const data = chart.data.datasets[0]?.data
        return Array.isArray(data) ? data.length : 0
      }

      return {
        update(next: ChartRenderOptions): void {
          const nextConfig = buildChartConfiguration(next, palette)
          // Chart.js can't swap a chart's geometry in place, so recreate when
          // the kind changes; otherwise patch the data and re-render.
          if (currentType !== nextConfig.type) {
            chart.destroy()
            chart = new Chart(canvas, nextConfig)
            currentType = nextConfig.type
            return
          }
          chart.data = nextConfig.data
          chart.update()
        },
        fractionAt(clientX: number): number | null {
          const area = chart.chartArea
          const scale = chart.scales.x
          if (!area || !scale || area.right <= area.left) {
            return null
          }
          const x = clientX - canvas.getBoundingClientRect().left
          if (x < area.left || x > area.right) {
            return null
          }
          const count = sampleCount()
          if (count <= 1) {
            return 0
          }
          const value = scale.getValueForPixel(x)
          if (typeof value !== 'number' || Number.isNaN(value)) {
            return null
          }
          return Math.min(1, Math.max(0, value / (count - 1)))
        },
        cursorGeometry(fraction: number): ChartCursorGeometry | null {
          const area = chart.chartArea
          const scale = chart.scales.x
          const count = sampleCount()
          if (!area || !scale || count <= 0 || area.bottom <= area.top) {
            return null
          }
          const left = scale.getPixelForValue(indexAtFraction(count, fraction))
          if (left < area.left || left > area.right) {
            return null
          }
          return { left, top: area.top, height: area.bottom - area.top }
        },
        destroy(): void {
          chart.destroy()
        },
      }
    },
  }
}
