import { beforeEach, describe, expect, it, vi } from 'vitest'

import { apiFetch } from '@/services/http'
import { fetchActivitySummary } from '@/features/summary/services/summary'
import {
  formatPeriodDate,
  monthEnd,
  monthLabel,
  monthNameLabel,
  monthStart,
  shiftMonths,
  shiftWeeks,
  weekdayLabel,
  weekEnd,
  weekStart,
  yearRange,
} from '@/features/summary/utils/period'
import {
  combineSummaryMetric,
  formatSummaryCalories,
  formatSummaryDistance,
  formatSummaryDuration,
  formatSummaryElevation,
} from '@/features/summary/utils/summaryFormat'

vi.mock('@/services/http', () => ({
  apiFetch: vi.fn<typeof apiFetch>(),
}))

/** Shared metric block reused across the mocked summary responses. */
const metrics = {
  total_distance: 10000,
  total_duration: 3600,
  total_elevation_gain: 100,
  total_calories: 500,
  activity_count: 2,
}

beforeEach(() => {
  vi.mocked(apiFetch).mockReset()
})

describe('fetchActivitySummary', () => {
  it('requests the week endpoint with date + type and maps day-of-week buckets', async () => {
    vi.mocked(apiFetch).mockResolvedValueOnce({
      ...metrics,
      breakdown: [
        { ...metrics, day_of_week: 0 },
        { ...metrics, day_of_week: 5 },
      ],
      type_breakdown: [{ ...metrics, activity_type_id: 1, activity_type: 'Run' }],
    })

    const result = await fetchActivitySummary('week', { date: '2024-06-10', typeName: 'Run' })

    expect(apiFetch).toHaveBeenCalledWith(
      '/activities/summaries?period=week&date=2024-06-10&type=Run',
      expect.objectContaining({ signal: undefined }),
    )
    expect(result.totals).toEqual({
      totalDistance: 10000,
      totalDuration: 3600,
      totalElevationGain: 100,
      totalCalories: 500,
      activityCount: 2,
    })
    expect(result.breakdown.map((row) => row.bucket)).toEqual([0, 5])
    expect(result.typeBreakdown[0]).toMatchObject({ activityType: 1, activityTypeName: 'Run' })
  })

  it('requests the month endpoint and maps week-number buckets', async () => {
    vi.mocked(apiFetch).mockResolvedValueOnce({
      ...metrics,
      breakdown: [{ ...metrics, week_number: 23 }],
      type_breakdown: null,
    })

    const result = await fetchActivitySummary('month', { date: '2024-06-01' })

    expect(apiFetch).toHaveBeenCalledWith(
      '/activities/summaries?period=month&date=2024-06-01',
      expect.objectContaining({ signal: undefined }),
    )
    expect(result.breakdown[0]?.bucket).toBe(23)
    expect(result.typeBreakdown).toEqual([])
  })

  it('requests the year endpoint with the year query and maps month-number buckets', async () => {
    vi.mocked(apiFetch).mockResolvedValueOnce({
      ...metrics,
      breakdown: [{ ...metrics, month_number: 12 }],
      type_breakdown: [],
    })

    const result = await fetchActivitySummary('year', { year: 2024 })

    expect(apiFetch).toHaveBeenCalledWith(
      '/activities/summaries?period=year&year=2024',
      expect.objectContaining({ signal: undefined }),
    )
    expect(result.breakdown[0]?.bucket).toBe(12)
  })

  it('requests the lifetime endpoint with no query and maps year-number buckets', async () => {
    vi.mocked(apiFetch).mockResolvedValueOnce({
      ...metrics,
      breakdown: [{ ...metrics, year_number: 2023 }],
      type_breakdown: [],
    })

    const result = await fetchActivitySummary('lifetime')

    expect(apiFetch).toHaveBeenCalledWith(
      '/activities/summaries?period=lifetime',
      expect.objectContaining({ signal: undefined }),
    )
    expect(result.breakdown[0]?.bucket).toBe(2023)
  })

  it('omits the date query for the week view when no date and a blank type are given', async () => {
    vi.mocked(apiFetch).mockResolvedValueOnce({ ...metrics, breakdown: [], type_breakdown: [] })

    await fetchActivitySummary('week', { typeName: '  ' })

    expect(apiFetch).toHaveBeenCalledWith(
      '/activities/summaries?period=week',
      expect.objectContaining({ signal: undefined }),
    )
  })

  it('returns an all-zero summary when the body is null', async () => {
    vi.mocked(apiFetch).mockResolvedValueOnce(null)

    await expect(fetchActivitySummary('lifetime')).resolves.toEqual({
      totals: {
        totalDistance: 0,
        totalDuration: 0,
        totalElevationGain: 0,
        totalCalories: 0,
        activityCount: 0,
      },
      breakdown: [],
      typeBreakdown: [],
    })
  })
})

describe('period boundaries', () => {
  it('computes Monday-start week boundaries with an inclusive Sunday end', () => {
    // 2024-06-12 is a Wednesday.
    expect(weekStart('2024-06-12', 'monday')).toBe('2024-06-10')
    expect(weekEnd('2024-06-12', 'monday')).toBe('2024-06-16')
  })

  it('keeps a Monday as its own week start and maps Sunday back to it', () => {
    expect(weekStart('2024-06-10', 'monday')).toBe('2024-06-10')
    expect(weekStart('2024-06-16', 'monday')).toBe('2024-06-10')
  })

  it('shifts weeks by whole weeks', () => {
    expect(shiftWeeks('2024-06-10', -1)).toBe('2024-06-03')
    expect(shiftWeeks('2024-06-10', 1)).toBe('2024-06-17')
  })

  it('computes inclusive month boundaries across leap years', () => {
    expect(monthStart('2024-06')).toBe('2024-06-01')
    expect(monthEnd('2024-06')).toBe('2024-06-30')
    expect(monthEnd('2024-02')).toBe('2024-02-29')
    expect(monthEnd('2023-02')).toBe('2023-02-28')
  })

  it('shifts months with year rollover in both directions', () => {
    expect(shiftMonths('2024-01', -1)).toBe('2023-12')
    expect(shiftMonths('2024-12', 1)).toBe('2025-01')
  })

  it('returns an inclusive calendar-year range', () => {
    expect(yearRange(2024)).toEqual({ startDate: '2024-01-01', endDate: '2024-12-31' })
  })
})

describe('period labels', () => {
  it('formats dates in UTC so the day never drifts with the timezone', () => {
    expect(formatPeriodDate('2024-06-10', 'en')).toBe('Jun 10, 2024')
    expect(monthLabel('2024-06-01', 'en')).toBe('June 2024')
  })

  it('localizes Monday-based weekday and month names', () => {
    expect(weekdayLabel(0, 'en')).toBe('Monday')
    expect(weekdayLabel(6, 'en')).toBe('Sunday')
    expect(monthNameLabel(1, 'en')).toBe('January')
    expect(monthNameLabel(12, 'en')).toBe('December')
  })
})

describe('summary formatters', () => {
  it('formats distance in km and miles to two decimals', () => {
    expect(formatSummaryDistance(12500, 'metric')).toEqual({ value: '12.50', unit: 'km' })
    expect(formatSummaryDistance(12500, 'imperial')).toEqual({ value: '7.77', unit: 'mi' })
  })

  it('formats elevation rounded in metres and feet', () => {
    expect(formatSummaryElevation(123.4, 'metric')).toEqual({ value: '123', unit: 'm' })
    expect(formatSummaryElevation(100, 'imperial')).toEqual({ value: '328', unit: 'ft' })
  })

  it('formats duration as a compact clock', () => {
    expect(formatSummaryDuration(3661)).toEqual({ value: '1h 1m', unit: '' })
    expect(formatSummaryDuration(600)).toEqual({ value: '10m', unit: '' })
    expect(formatSummaryDuration(0)).toEqual({ value: '0m', unit: '' })
  })

  it('formats calories grouped into thousands', () => {
    expect(formatSummaryCalories(1234)).toEqual({ value: '1,234', unit: 'kcal' })
    expect(formatSummaryCalories(999)).toEqual({ value: '999', unit: 'kcal' })
  })

  it('combines a metric value and unit, omitting an empty unit', () => {
    expect(combineSummaryMetric({ value: '12.50', unit: 'km' })).toBe('12.50 km')
    expect(combineSummaryMetric({ value: '5', unit: '' })).toBe('5')
  })
})
