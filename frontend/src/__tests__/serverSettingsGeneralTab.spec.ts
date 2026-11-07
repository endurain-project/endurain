import { defineComponent, h } from 'vue'
import { QueryClient, VueQueryPlugin } from '@tanstack/vue-query'
import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import type { ServerSettings, ServerSettingsUpdate } from '@/features/serverSettings/types'

import i18n from '@/i18n'
import { useToasts } from '@/composables/useToasts'
import GeneralTab from '@/features/serverSettings/components/tabs/GeneralTab.vue'
import {
  provideServerSettingsForm,
  useServerSettingsForm,
} from '@/features/serverSettings/composables/useServerSettingsForm'
import { HttpError } from '@/services/http'

const mutateAsync = vi.fn<(settings: ServerSettingsUpdate) => Promise<ServerSettings>>()

vi.mock('@/features/serverSettings/composables/useServerSettings', async (importOriginal) => ({
  ...(await importOriginal<
    typeof import('@/features/serverSettings/composables/useServerSettings')
  >()),
  useUpdateServerSettingsMutation: () => ({ mutateAsync }),
}))

/** Loaded server settings, overridable per case. */
function makeSettings(overrides: Partial<ServerSettings> = {}): ServerSettings {
  return {
    id: 1,
    version: 3,
    units: 'metric',
    currency: 'euro',
    numRecordsPerPage: 25,
    publicShareableLinks: false,
    publicShareableLinksUserInfo: false,
    loginPhotoSet: false,
    signupEnabled: false,
    signupRequireAdminApproval: true,
    signupRequireEmailVerification: true,
    ssoEnabled: false,
    localLoginEnabled: true,
    ssoAutoRedirect: false,
    tileserverUrl: 'https://tile.openstreetmap.org/{z}/{x}/{y}.png',
    tileserverAttribution: '© OpenStreetMap',
    tileserverApiKeySet: false,
    tileserverRegenerateThumbnailsOnChange: false,
    mapBackgroundColor: '#dddddd',
    passwordLengthRegularUsers: 15,
    passwordLengthAdminUsers: 15,
    geocodingService: 'nominatim',
    geocodingHost: null,
    geocodingUseHttps: true,
    geocodingRateLimit: 1,
    sessionIdleTimeoutEnabled: false,
    sessionIdleTimeoutHours: 1,
    sessionAbsoluteTimeoutHours: 720,
    accessTokenExpireMinutes: 15,
    refreshTokenExpireDays: 7,
    apiKeyMaxLifetimeDays: 365,
    readNotificationRetentionDays: 90,
    auditRetentionDays: 90,
    auditLegalHold: false,
    geocodingApiKeySet: false,
    envManaged: {},
    ...overrides,
  }
}

/**
 * Mounts the general tab inside the real server settings form.
 *
 * @param settings - The loaded settings the form starts from.
 * @returns The mounted wrapper.
 */
function mountGeneralTab(settings: ServerSettings = makeSettings()) {
  const Host = defineComponent({
    setup() {
      provideServerSettingsForm(useServerSettingsForm({ settings, templates: [] }))
      return () => h(GeneralTab)
    },
  })
  return mount(Host, {
    global: { plugins: [i18n, [VueQueryPlugin, { queryClient: new QueryClient() }]] },
  })
}

describe('GeneralTab audit trail retention', () => {
  beforeEach(() => {
    mutateAsync.mockReset()
    mutateAsync.mockResolvedValue(makeSettings())
  })

  it('shows the retention and legal hold with their hints', () => {
    const wrapper = mountGeneralTab(makeSettings({ auditRetentionDays: 365, auditLegalHold: true }))

    const retention = wrapper.get('[data-setting="retention-audit-trail"]')
    expect(retention.get('input').element.value).toBe('365')
    expect(retention.text()).toContain('0 keeps everything')
    expect(retention.text()).toContain('minimum is 30 days')
    const hold = wrapper.get('[data-setting="retention-audit-legal-hold"]')
    expect(hold.get<HTMLInputElement>('input[role="switch"]').element.checked).toBe(true)
    expect(wrapper.text()).toContain('pauses all pruning of the audit trail')
  })

  it.each(['1', '29', '36501', 'abc'])('refuses %s and does not save', async (value) => {
    const wrapper = mountGeneralTab()

    await wrapper.get('[data-setting="retention-audit-trail"] input').setValue(value)
    await wrapper.get('form').trigger('submit')
    await flushPromises()

    expect(wrapper.get('[data-setting="retention-audit-trail"]').text()).toContain(
      'Enter 0, or a whole number between 30 and 36500.',
    )
    expect(mutateAsync).not.toHaveBeenCalled()
  })

  it.each([
    ['0', 0],
    ['30', 30],
    ['36500', 36500],
  ])('saves %s with the legal hold and the version it read', async (value, days) => {
    const wrapper = mountGeneralTab()

    await wrapper.get('[data-setting="retention-audit-trail"] input').setValue(value)
    await wrapper.get('[data-setting="retention-audit-legal-hold"] input').setValue(true)
    await wrapper.get('form').trigger('submit')
    await flushPromises()

    expect(mutateAsync).toHaveBeenCalledOnce()
    expect(mutateAsync.mock.calls[0]?.[0]).toMatchObject({
      version: 3,
      auditRetentionDays: days,
      auditLegalHold: true,
    })
  })

  it('reports a stale copy when the save is refused with 412', async () => {
    mutateAsync.mockRejectedValue(new HttpError(412, 'Precondition Failed'))
    const wrapper = mountGeneralTab()

    await wrapper.get('[data-setting="retention-audit-legal-hold"] input').setValue(true)
    await wrapper.get('form').trigger('submit')
    await flushPromises()

    const { toasts } = useToasts()
    expect(toasts.value[toasts.value.length - 1]).toMatchObject({
      kind: 'error',
      message: i18n.global.t('settings.server.staleError'),
    })
  })
})
