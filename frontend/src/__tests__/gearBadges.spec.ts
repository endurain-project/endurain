import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'

import type { Gear } from '@/features/gears/types'

import i18n from '@/i18n'
import GearBadges from '@/features/gears/components/GearBadges.vue'

/** Builds a minimal active gear with no integration link, overridable per case. */
function makeGear(overrides: Partial<Gear> = {}): Gear {
  return {
    id: 1,
    userId: 1,
    gearType: 1,
    nickname: 'Road bike',
    brand: null,
    model: null,
    active: true,
    createdAt: null,
    initialKms: null,
    purchaseValue: null,
    stravaGearId: null,
    garminConnectGearId: null,
    version: 1,
    ...overrides,
  }
}

function mountBadges(gear: Gear) {
  return mount(GearBadges, { props: { gear }, global: { plugins: [i18n] } })
}

describe('GearBadges', () => {
  it('renders nothing for an active gear with no integration source', () => {
    const wrapper = mountBadges(makeGear())
    expect(wrapper.find('div').exists()).toBe(false)
    expect(wrapper.text()).toBe('')
  })

  it('shows the inactive badge when the gear is inactive', () => {
    const wrapper = mountBadges(makeGear({ active: false }))
    expect(wrapper.text()).toContain('Inactive')
  })

  it('shows the Strava badge when linked to a Strava gear', () => {
    const wrapper = mountBadges(makeGear({ stravaGearId: 'g123' }))
    expect(wrapper.text()).toContain('Strava')
    expect(wrapper.text()).not.toContain('Garmin')
  })

  it('shows the Garmin Connect badge when linked to a Garmin gear', () => {
    const wrapper = mountBadges(makeGear({ garminConnectGearId: 'abc' }))
    expect(wrapper.text()).toContain('Garmin Connect')
    expect(wrapper.text()).not.toContain('Strava')
  })

  it('shows every applicable badge together', () => {
    const wrapper = mountBadges(
      makeGear({ active: false, stravaGearId: 'g1', garminConnectGearId: 'g2' }),
    )
    const text = wrapper.text()
    expect(text).toContain('Inactive')
    expect(text).toContain('Strava')
    expect(text).toContain('Garmin Connect')
  })
})
