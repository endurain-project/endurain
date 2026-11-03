import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { effectScope, ref } from 'vue'

import { useNow } from '@/composables/useNow'

describe('useNow', () => {
  beforeEach(() => {
    vi.useFakeTimers()
    vi.setSystemTime(new Date('2026-10-30T12:00:00Z'))
  })
  afterEach(() => {
    vi.useRealTimers()
  })

  it('advances on every interval', () => {
    const scope = effectScope()
    const now = scope.run(() => useNow(1000))!
    const start = now.value
    vi.advanceTimersByTime(3000)
    expect(now.value).toBe(start + 3000)
    scope.stop()
  })

  it('does not tick while the interval is null and resumes when it is set', async () => {
    const interval = ref<number | null>(null)
    const scope = effectScope()
    const now = scope.run(() => useNow(interval))!
    const start = now.value
    vi.advanceTimersByTime(5000)
    expect(now.value).toBe(start)

    interval.value = 1000
    await Promise.resolve()
    vi.advanceTimersByTime(2000)
    expect(now.value).toBe(start + 5000 + 2000)

    interval.value = null
    await Promise.resolve()
    const stopped = now.value
    vi.advanceTimersByTime(5000)
    expect(now.value).toBe(stopped)
    scope.stop()
  })

  it('stops ticking when its scope is disposed', () => {
    const scope = effectScope()
    const now = scope.run(() => useNow(1000))!
    scope.stop()
    const stopped = now.value
    vi.advanceTimersByTime(5000)
    expect(now.value).toBe(stopped)
    expect(vi.getTimerCount()).toBe(0)
  })
})
