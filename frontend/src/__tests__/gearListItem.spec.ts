import { describe, expect, it } from 'vitest'

import { mount } from '@vue/test-utils'

import type { Gear } from '@/features/gears/types'

import i18n from '@/i18n'
import GearListItem from '@/features/gears/components/GearListItem.vue'

const gear: Gear = {
  id: '00000000-0000-4000-8000-000000000002',
  userId: '00000000-0000-4000-8000-000000000001',
  gearType: 'bike',
  nickname: 'Road',
  brand: null,
  model: null,
  active: true,
  acquiredOn: null,
  initialKms: null,
  purchaseValue: null,
  stravaGearId: null,
  garminConnectGearId: null,
  version: 5,
}

function mountItem(deleting: boolean) {
  return mount(GearListItem, {
    props: { gear, deleting },
    global: { plugins: [i18n], stubs: { RouterLink: { template: '<a><slot /></a>' } } },
  })
}

describe('GearListItem', () => {
  it('keeps its actions enabled while the gear is not being deleted', () => {
    const wrapper = mountItem(false)

    expect(
      wrapper.findAll('button').every((button) => button.attributes('disabled') === undefined),
    ).toBe(true)
    expect(wrapper.text()).not.toContain(i18n.global.t('gears.delete.deleting'))
  })

  it('shows the gear as deleting and disables its actions while its deletion runs', () => {
    const wrapper = mountItem(true)

    expect(wrapper.text()).toContain(i18n.global.t('gears.delete.deleting'))
    const buttons = wrapper.findAll('button')
    expect(buttons).toHaveLength(2)
    expect(buttons.every((button) => button.attributes('disabled') !== undefined)).toBe(true)
  })
})
