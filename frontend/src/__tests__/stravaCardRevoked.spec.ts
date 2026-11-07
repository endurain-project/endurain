import { describe, expect, it } from 'vitest'

import { mount } from '@vue/test-utils'
import { QueryClient, VueQueryPlugin } from '@tanstack/vue-query'

import i18n from '@/i18n'
import StravaCard from '@/features/integrations/components/StravaCard.vue'

function mountCard(props: {
  linked: boolean
  revokedAt: string | null
  dataDeletionAt: string | null
}) {
  return mount(StravaCard, {
    props: { ...props, integrationsVersion: 1 },
    global: { plugins: [i18n, [VueQueryPlugin, { queryClient: new QueryClient() }]] },
  })
}

describe('StravaCard after Strava access was revoked', () => {
  it('shows when access ended and when the data is deleted, with the reconnect action', () => {
    const wrapper = mountCard({
      linked: false,
      revokedAt: '2026-11-05T09:30:00Z',
      dataDeletionAt: '2026-11-12T09:30:00Z',
    })

    const notice = wrapper.get('[role="status"]').text()
    expect(notice).toContain('Strava access ended on')
    expect(notice).toContain('will be deleted on')
    expect(wrapper.get('button').text()).toBe('Reconnect')
  })

  it('shows no notice while access is intact', () => {
    const wrapper = mountCard({ linked: false, revokedAt: null, dataDeletionAt: null })

    expect(wrapper.find('[role="status"]').exists()).toBe(false)
    expect(wrapper.get('button').text()).toBe('Connect')
  })

  it('shows no notice for a linked account', () => {
    const wrapper = mountCard({ linked: true, revokedAt: null, dataDeletionAt: null })

    expect(wrapper.find('[role="status"]').exists()).toBe(false)
  })
})
