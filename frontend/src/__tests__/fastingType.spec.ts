import { describe, expect, it } from 'vitest'

import { mount } from '@vue/test-utils'

import type { FastingEntry } from '@/features/health/types'

import i18n from '@/i18n'
import HealthFastingActiveCard from '@/features/health/components/HealthFastingActiveCard.vue'
import HealthFastingListItem from '@/features/health/components/HealthFastingListItem.vue'

const entry = {
  id: 1,
  version: 1,
  fastingType: 'OMAD',
  status: 'in_progress',
  fastStartTime: '2026-10-30T11:00:00Z',
} as unknown as FastingEntry
const label = i18n.global.t('health.fasting.types.OMAD')

describe('fasting type display', () => {
  it('shows the translated label in the list item', () => {
    const wrapper = mount(HealthFastingListItem, {
      props: { entry },
      global: { plugins: [i18n] },
    })
    expect(wrapper.text()).toContain(label)
  })

  it('shows the translated label in the active card', () => {
    const wrapper = mount(HealthFastingActiveCard, {
      props: { entry, completing: false },
      global: { plugins: [i18n] },
    })
    expect(wrapper.text()).toContain(label)
    wrapper.unmount()
  })
})
