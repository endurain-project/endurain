import { describe, expect, it } from 'vitest'
import { defineComponent } from 'vue'
import { flushPromises, mount } from '@vue/test-utils'
import { createMemoryHistory, createRouter } from 'vue-router'

import { useTabQuery } from '@/composables/useTabQuery'
import { profileTabForAction } from '@/features/profile/tabs'
import { securityTabForAction } from '@/features/security/tabs'

describe('securityTabForAction', () => {
  it('opens the tab of the card that started the step-up', () => {
    expect(securityTabForAction('email_change')).toBe('account')
    expect(securityTabForAction('mfa_enable')).toBe('account')
    expect(securityTabForAction('api_key_create')).toBe('sessions')
    expect(securityTabForAction('profile_device_forget')).toBe('sessions')
    expect(securityTabForAction('account_delete')).toBe('danger')
  })

  it('falls back to the default tab for an action the page does not own', () => {
    expect(securityTabForAction('admin_user_edit')).toBe('account')
  })
})

describe('profileTabForAction', () => {
  it('opens the privacy tab for the data export and the default tab otherwise', () => {
    expect(profileTabForAction('profile_export')).toBe('privacy')
    expect(profileTabForAction('email_change')).toBe('profile')
  })
})

describe('useTabQuery', () => {
  async function setup(initial: string) {
    const router = createRouter({
      history: createMemoryHistory(),
      routes: [{ path: '/', component: { template: '<div />' } }],
    })
    await router.push(initial)
    let tabs!: ReturnType<typeof useTabQuery<'a' | 'b'>>
    mount(
      defineComponent({
        setup() {
          tabs = useTabQuery(['a', 'b'] as const, 'a')
          return () => null
        },
      }),
      { global: { plugins: [router] } },
    )
    return { router, tabs }
  }

  it('reads the tab from the URL and falls back for an unknown one', async () => {
    expect((await setup('/?tab=b')).tabs.activeTab.value).toBe('b')
    expect((await setup('/?tab=nope')).tabs.activeTab.value).toBe('a')
    expect((await setup('/')).tabs.activeTab.value).toBe('a')
  })

  it('switches tab keeping the other query params', async () => {
    const { router, tabs } = await setup('/?keep=1')
    await tabs.selectTab('b')
    await flushPromises()
    expect(router.currentRoute.value.query).toEqual({ keep: '1', tab: 'b' })
    expect(tabs.activeTab.value).toBe('b')
  })
})
