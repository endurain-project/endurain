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
    geocodingApiKeySet: false,
    envManaged: {},
    stepUpFields: ['publicShareableLinksUserInfo', 'requireMfa'],
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
    const { wrapper, form } = mountGeneralTab(makeSettings({ stepUpFields: ['ssoEnabled'] }))

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

    form.values.requireMfa = 'everyone'
    await wrapper.get('form').trigger('submit')
    await flushPromises()
    await form.confirmStepUp(STEP_UP)

    expect(form.isStepUpOpen.value).toBe(true)
  })

  it('reports a stale copy when the save is refused with 412', async () => {
    mutateAsync.mockRejectedValue(new HttpError(412, 'Precondition Failed'))
    const { wrapper, form } = mountGeneralTab()

    form.values.requireMfa = 'everyone'
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
