import { defineComponent, h, reactive, ref } from 'vue'
import { mount } from '@vue/test-utils'
import { describe, expect, it, vi } from 'vitest'

import i18n from '@/i18n'
import AccessTab from '@/features/serverSettings/components/tabs/AccessTab.vue'
import {
  provideServerSettingsForm,
  type ServerSettingsFormContext,
} from '@/features/serverSettings/composables/useServerSettingsForm'

/**
 * Mounts the access tab with a minimal form context.
 *
 * @param idleEnabled - Whether the idle timeout switch is on.
 * @returns The mounted wrapper.
 */
function mountAccessTab(idleEnabled: boolean) {
  const context = {
    values: reactive({
      passwordLengthRegularUsers: 15,
      passwordLengthAdminUsers: 15,
      passwordBreachCheckEnabled: false,
      sessionIdleTimeoutEnabled: idleEnabled,
      sessionIdleTimeoutHours: '24',
      sessionAbsoluteTimeoutHours: '720',
      apiKeyMaxLifetimeDays: '365',
    }),
    errors: reactive({}),
    isSubmitting: ref(false),
    handleSubmit: vi.fn<() => void>(),
    handleBlur: vi.fn<() => void>(),
    envVar: () => undefined,
    envHint: () => undefined,
    envNames: () => [],
  } as unknown as ServerSettingsFormContext
  const Host = defineComponent({
    setup() {
      provideServerSettingsForm(context)
      return () => h(AccessTab)
    },
  })
  return mount(Host, { global: { plugins: [i18n] } })
}

describe('AccessTab session timeouts', () => {
  it('keeps the absolute timeout editable while the idle timeout switch is off', () => {
    const wrapper = mountAccessTab(false)

    expect(
      wrapper.get('[data-setting="session-absolute-hours"] input').attributes('disabled'),
    ).toBeUndefined()
    expect(
      wrapper.get('[data-setting="session-idle-hours"] input').attributes('disabled'),
    ).toBeDefined()
  })

  it('enables the idle timeout input when the switch is on', () => {
    const wrapper = mountAccessTab(true)

    expect(
      wrapper.get('[data-setting="session-idle-hours"] input').attributes('disabled'),
    ).toBeUndefined()
  })
})

describe('AccessTab API key lifetime', () => {
  it('shows the maximum API key lifetime among the session settings', () => {
    const wrapper = mountAccessTab(false)

    const input = wrapper.get('[data-setting="session-api-key-days"] input')
    expect((input.element as HTMLInputElement).value).toBe('365')
    expect(input.attributes('disabled')).toBeUndefined()
  })
})

describe('AccessTab password policy', () => {
  it('offers only the two minimum-length controls, from 8 to 128', () => {
    const wrapper = mountAccessTab(true)

    expect(wrapper.find('[data-setting="password-type"]').exists()).toBe(false)
    for (const setting of ['password-length-regular', 'password-length-admin']) {
      const options = wrapper.findAll(`[data-setting="${setting}"] option`)
      expect(options[0]?.text()).toBe('8')
      expect(options[options.length - 1]?.text()).toBe('128')
    }
  })
  it('offers the breached-password check and says what it sends', () => {
    const wrapper = mountAccessTab(true)

    expect(wrapper.find('[data-setting="password-breach-check"]').exists()).toBe(true)
    expect(wrapper.get('[data-setting="section-password"]').text()).toContain('haveibeenpwned.com')
  })
})
