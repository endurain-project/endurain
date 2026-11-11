import { defineComponent, h } from 'vue'
import { QueryClient, VueQueryPlugin } from '@tanstack/vue-query'
import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import type { StepUpInput } from '@/features/security/types'
import type { ServerSettings, ServerSettingsUpdate } from '@/features/serverSettings/types'

import i18n from '@/i18n'
import { useToasts } from '@/composables/useToasts'
import GeneralTab from '@/features/serverSettings/components/tabs/GeneralTab.vue'
import {
  provideServerSettingsForm,
  useServerSettingsForm,
} from '@/features/serverSettings/composables/useServerSettingsForm'
import { HttpError } from '@/services/http'

const mutateAsync =
  vi.fn<
    (variables: {
      settings: ServerSettingsUpdate
      stepUp: StepUpInput | null
    }) => Promise<ServerSettings>
  >()
const STEP_UP: StepUpInput = { currentPassword: 'admin-pw', mfaCode: null, idpReauth: null }

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
    signupSsoEnabled: false,
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
    passwordBreachCheckEnabled: false,
    requireMfa: 'off',
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
    stepUpFields: [
      'publicShareableLinksUserInfo',
      'auditRetentionDays',
      'auditLegalHold',
      'requireMfa',
    ],
    logsViewerEnabled: false,
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
  let form: ReturnType<typeof useServerSettingsForm> | undefined
  const Host = defineComponent({
    setup() {
      form = useServerSettingsForm({ settings, templates: [] })
      provideServerSettingsForm(form)
      return () => h(GeneralTab)
    },
  })
  const wrapper = mount(Host, {
    global: { plugins: [i18n, [VueQueryPlugin, { queryClient: new QueryClient() }]] },
  })
  if (!form) {
    throw new Error('the form was not created')
  }
  return { wrapper, form }
}

describe('GeneralTab audit trail retention', () => {
  beforeEach(() => {
    mutateAsync.mockReset()
    mutateAsync.mockResolvedValue(makeSettings())
  })

  it('shows the retention and legal hold with their hints', () => {
    const { wrapper } = mountGeneralTab(
      makeSettings({ auditRetentionDays: 365, auditLegalHold: true }),
    )

    const retention = wrapper.get('[data-setting="retention-audit-trail"]')
    expect(retention.get('input').element.value).toBe('365')
    expect(retention.text()).toContain('0 keeps everything')
    expect(retention.text()).toContain('minimum is 30 days')
    const hold = wrapper.get('[data-setting="retention-audit-legal-hold"]')
    expect(hold.get<HTMLInputElement>('input[role="switch"]').element.checked).toBe(true)
    expect(wrapper.text()).toContain('pauses all pruning of the audit trail')
  })

  it.each(['1', '29', '36501', 'abc'])('refuses %s and does not save', async (value) => {
    const { wrapper } = mountGeneralTab()

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
  ])('saves %s with the legal hold, the version it read and the step-up', async (value, days) => {
    const { wrapper, form } = mountGeneralTab()

    await wrapper.get('[data-setting="retention-audit-trail"] input').setValue(value)
    await wrapper.get('[data-setting="retention-audit-legal-hold"] input').setValue(true)
    await wrapper.get('form').trigger('submit')
    await flushPromises()

    // A security-relevant change waits for the administrator's step-up.
    expect(mutateAsync).not.toHaveBeenCalled()
    expect(form.isStepUpOpen.value).toBe(true)

    await form.confirmStepUp(STEP_UP)

    expect(mutateAsync).toHaveBeenCalledOnce()
    expect(mutateAsync.mock.calls[0]?.[0].stepUp).toEqual(STEP_UP)
    expect(mutateAsync.mock.calls[0]?.[0].settings).toMatchObject({
      version: 3,
      auditRetentionDays: days,
      auditLegalHold: true,
    })
  })

  it('waits for the step-up, then saves it, when the MFA requirement changes', async () => {
    const { wrapper, form } = mountGeneralTab()

    form.values.requireMfa = 'everyone'
    await wrapper.get('form').trigger('submit')
    await flushPromises()

    expect(mutateAsync).not.toHaveBeenCalled()
    expect(form.isStepUpOpen.value).toBe(true)

    await form.confirmStepUp(STEP_UP)

    expect(mutateAsync.mock.calls[0]?.[0].stepUp).toEqual(STEP_UP)
    expect(mutateAsync.mock.calls[0]?.[0].settings).toMatchObject({ requireMfa: 'everyone' })
  })

  it('waits for the step-up when public links start showing the owner', async () => {
    const { wrapper, form } = mountGeneralTab()

    form.values.publicShareableLinksUserInfo = true
    await wrapper.get('form').trigger('submit')
    await flushPromises()

    expect(mutateAsync).not.toHaveBeenCalled()
    expect(form.isStepUpOpen.value).toBe(true)
  })

  it('waits for the step-up only for the settings the server lists', async () => {
    const { wrapper, form } = mountGeneralTab(makeSettings({ stepUpFields: ['auditLegalHold'] }))

    form.values.publicShareableLinksUserInfo = true
    await wrapper.get('form').trigger('submit')
    await flushPromises()

    expect(form.isStepUpOpen.value).toBe(false)
    expect(mutateAsync).toHaveBeenCalledOnce()
  })

  it('saves a change to a setting that is not security-relevant without a step-up', async () => {
    const { wrapper, form } = mountGeneralTab()

    await wrapper.get('[data-setting="general-num-records"] select').setValue(50)
    await wrapper.get('form').trigger('submit')
    await flushPromises()

    expect(form.isStepUpOpen.value).toBe(false)
    expect(mutateAsync).toHaveBeenCalledOnce()
    expect(mutateAsync.mock.calls[0]?.[0]).toMatchObject({
      stepUp: null,
      settings: { numRecordsPerPage: 50 },
    })
  })

  it('keeps the step-up dialog open when the step-up is refused', async () => {
    mutateAsync.mockRejectedValue(
      new HttpError(403, 'Forbidden', undefined, 'urn:endurain:error:step-up-failed'),
    )
    const { wrapper, form } = mountGeneralTab()

    await wrapper.get('[data-setting="retention-audit-legal-hold"] input').setValue(true)
    await wrapper.get('form').trigger('submit')
    await flushPromises()
    await form.confirmStepUp(STEP_UP)

    expect(form.isStepUpOpen.value).toBe(true)
  })

  it('reports a stale copy when the save is refused with 412', async () => {
    mutateAsync.mockRejectedValue(new HttpError(412, 'Precondition Failed'))
    const { wrapper, form } = mountGeneralTab()

    await wrapper.get('[data-setting="retention-audit-legal-hold"] input').setValue(true)
    await wrapper.get('form').trigger('submit')
    await flushPromises()
    await form.confirmStepUp(STEP_UP)

    const { toasts } = useToasts()
    expect(toasts.value[toasts.value.length - 1]).toMatchObject({
      kind: 'error',
      message: i18n.global.t('settings.server.staleError'),
    })
  })
})
