import { describe, expect, it } from 'vitest'

import { setChartProvider, useChartProvider } from '@/composables/useChartProvider'
import {
  buildChartConfiguration,
  createChartJsChartProvider,
  DEFAULT_CHART_PALETTE,
} from '@/providers/chartJsChartProvider'

describe('buildChartConfiguration', () => {
  it('maps a line chart with smoothing and a flat translucent fill', () => {
    const config = buildChartConfiguration({
      kind: 'line',
      labels: ['a', 'b'],
      series: [{ label: 'Pace', data: [1, 2] }],
    })

    expect(config.type).toBe('line')
    expect(config.data.labels).toEqual(['a', 'b'])

    const dataset = config.data.datasets[0] as Record<string, unknown> | undefined
    expect(dataset?.label).toBe('Pace')
    expect(dataset?.data).toEqual([1, 2])
    expect(dataset?.fill).toBe(true)
    // Flat translucent fill (not a gradient), per the design system.
    expect(dataset?.backgroundColor).toBe('rgba(29, 158, 117, 0.15)')
    expect(dataset?.tension).toBe(0.3)
  })

  it('fills the area for area charts while staying a line type', () => {
    const config = buildChartConfiguration({
      kind: 'area',
      series: [{ label: 'Elevation', data: [3] }],
    })

    expect(config.type).toBe('line')
    const dataset = config.data.datasets[0] as Record<string, unknown> | undefined
    expect(dataset?.fill).toBe(true)
  })

  it('maps bar charts to the bar type', () => {
    const config = buildChartConfiguration({
      kind: 'bar',
      series: [{ label: 'Count', data: [5] }],
    })

    expect(config.type).toBe('bar')
  })

  it('renders a dashed series as a dashed line overlay regardless of chart kind', () => {
    const config = buildChartConfiguration({
      kind: 'bar',
      series: [
        { label: 'Count', data: [1, 2] },
        { label: 'Target', data: [3, 3], dashed: true },
      ],
    })

    expect(config.type).toBe('bar')
    const datasets = config.data.datasets as unknown as Record<string, unknown>[]
    // The data series keeps the chart's bar geometry (no explicit per-dataset type).
    expect(datasets[0]?.type).toBeUndefined()
    // The dashed target is overlaid as a line with a dash pattern and no fill.
    expect(datasets[1]?.type).toBe('line')
    expect(datasets[1]?.borderDash).toEqual([6, 6])
    expect(datasets[1]?.fill).toBe(false)
    expect(datasets[1]?.pointRadius).toBe(0)
  })

  it('assigns palette colours by series index and honours explicit colours', () => {
    const config = buildChartConfiguration({
      kind: 'line',
      series: [
        { label: 'A', data: [1] },
        { label: 'B', data: [2], color: '#abcdef' },
      ],
    })

    const datasets = config.data.datasets as unknown as Record<string, unknown>[]
    expect(datasets[0]?.borderColor).toBe(DEFAULT_CHART_PALETTE[0])
    expect(datasets[1]?.borderColor).toBe('#abcdef')
  })

  it('defaults labels to an empty array when omitted', () => {
    const config = buildChartConfiguration({ kind: 'line', series: [] })
    expect(config.data.labels).toEqual([])
  })

  it('shows the legend only for multi-series charts', () => {
    const single = buildChartConfiguration({
      kind: 'line',
      series: [{ label: 'A', data: [1] }],
    })
    const multi = buildChartConfiguration({
      kind: 'line',
      series: [
        { label: 'A', data: [1] },
        { label: 'B', data: [2] },
      ],
    })

    expect(single.options?.plugins?.legend?.display).toBe(false)
    expect(multi.options?.plugins?.legend?.display).toBe(true)
  })

  it('applies the value formatter to y-axis ticks and inverts the axis when requested', () => {
    const config = buildChartConfiguration({
      kind: 'line',
      series: [{ label: 'HR', data: [1] }],
      valueFormat: (value) => `${value} bpm`,
      invertY: true,
    })

    const y = config.options?.scales?.y as Record<string, unknown> | undefined
    expect(y?.reverse).toBe(true)
    const ticks = y?.ticks as { callback?: (value: number) => string } | undefined
    expect(ticks?.callback?.(120)).toBe('120 bpm')
  })

  it('appends the x-axis unit to the tooltip title', () => {
    const config = buildChartConfiguration({
      kind: 'line',
      series: [{ label: 'HR', data: [1] }],
      labels: ['0.7'],
      xUnit: 'km',
    })
    const tooltip = config.options?.plugins?.tooltip as
      { callbacks?: { title?: (items: { label: string }[]) => string } } | undefined
    expect(tooltip?.callbacks?.title?.([{ label: '0.7' }])).toBe('0.7 km')
  })

  it('leaves the y-axis upright without explicit options', () => {
    const config = buildChartConfiguration({ kind: 'line', series: [{ label: 'A', data: [1] }] })
    const y = config.options?.scales?.y as Record<string, unknown> | undefined
    expect(y?.reverse).toBe(false)
  })

  it('adds pan/zoom config when zoom is enabled and omits it otherwise', () => {
    const zoomed = buildChartConfiguration({
      kind: 'line',
      series: [{ label: 'HR', data: [1] }],
      zoom: true,
    })
    const zoom = zoomed.options?.plugins?.zoom as { pan?: { enabled?: boolean } } | undefined
    expect(zoom?.pan?.enabled).toBe(true)

    const plain = buildChartConfiguration({ kind: 'line', series: [{ label: 'A', data: [1] }] })
    expect(plain.options?.plugins?.zoom).toBeUndefined()
  })
})

describe('createChartJsChartProvider', () => {
  it('names the provider and registers as available behind the seam', () => {
    const provider = createChartJsChartProvider()
    expect(provider.name).toBe('chartjs')

    setChartProvider(provider)
    const { provider: active, isAvailable } = useChartProvider()
    expect(active.name).toBe('chartjs')
    expect(isAvailable).toBe(true)
  })
})
