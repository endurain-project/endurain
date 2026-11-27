import { afterEach, describe, expect, it } from 'vitest'

import { hrZoneColor } from '@/features/activities/utils/hrZones'

describe('hrZoneColor', () => {
  afterEach(() => {
    document.documentElement.style.cssText = ''
  })

  it('reads zones 1, 2, 3 and 5 from the design tokens', () => {
    const root = document.documentElement
    root.style.setProperty('--color-info', '#111111')
    root.style.setProperty('--color-goal', '#222222')
    root.style.setProperty('--color-effort', '#333333')
    root.style.setProperty('--color-hr', '#555555')
    expect([1, 2, 3, 5].map(hrZoneColor)).toEqual(['#111111', '#222222', '#333333', '#555555'])
  })

  it('reads zone 4 from its design token, falling back to orange', () => {
    expect(hrZoneColor(4)).toBe('#f97316')
    document.documentElement.style.setProperty('--color-hr-zone-4', '#444444')
    expect(hrZoneColor(4)).toBe('#444444')
  })

  it('falls back to the top-zone colour out of range', () => {
    document.documentElement.style.setProperty('--color-hr', '#555555')
    expect(hrZoneColor(9)).toBe('#555555')
  })
})
