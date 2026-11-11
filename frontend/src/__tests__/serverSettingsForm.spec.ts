import { defineComponent, h } from 'vue'
import { mount } from '@vue/test-utils'
import { describe, expect, it, vi } from 'vitest'

import i18n from '@/i18n'
import { mapServerSettings } from '@/features/serverSettings/services/serverSettings'
import type { ServerSettingsDto } from '@/features/serverSettings/types'
import { useServerSettingsForm } from '@/features/serverSettings/composables/useServerSettingsForm'

vi.mock('@/composables/useToasts', () => ({ useToasts: () => ({}) }))
vi.mock('@/features/security/composables/useIdpStepUp', () => ({
  isStepUpFailed: vi.fn<() => boolean>(),
  isStepUpLocked: vi.fn<() => boolean>(),
  useIdpReauthChallenge: () => vi.fn<() => boolean>(),
}))
vi.mock('@/features/serverSettings/composables/useMailStepUpResume', () => ({
  useSettingsStepUpResume: () => undefined,
}))
vi.mock('@/features/serverSettings/composables/useServerSettings', () => ({
  useUpdateServerSettingsMutation: () => ({
    isPending: { value: false },
    mutateAsync: vi.fn<() => Promise<void>>(),
  }),
}))
vi.mock('@/features/security/composables/useAdminStepUp', () => ({
  useResumeOnce: vi.fn<() => void>(),
}))

/** Builds a full settings wire payload with the session policy given. */
function makeSettings(overrides: Partial<ServerSettingsDto>) {
  return mapServerSettings({
    id: 1,
    version: 1,
    units: 'metric',
    currency: 'euro',
    num_records_per_page: 25,
    public_shareable_links: false,
    public_shareable_links_user_info: false,
    login_photo_set: false,
    signup_enabled: false,
    signup_sso_enabled: false,
    signup_require_admin_approval: true,
    signup_require_email_verification: true,
    sso_enabled: false,
    local_login_enabled: true,
    sso_auto_redirect: false,
    tileserver_url: 'https://tile.test/{z}/{x}/{y}.png',
    tileserver_attribution: '© Test',
    tileserver_api_key_set: false,
    tileserver_regenerate_thumbnails_on_change: false,
    map_background_color: '#dddddd',
    password_length_regular_users: 8,
    password_length_admin_users: 12,
    password_breach_check_enabled: false,
    require_mfa: 'off',
    geocoding_service: 'nominatim',
    geocoding_host: null,
    geocoding_use_https: true,
    geocoding_rate_limit: 1,
    session_idle_timeout_enabled: false,
    session_idle_timeout_hours: 1,
    session_absolute_timeout_hours: 24,
    access_token_expire_minutes: 15,
    refresh_token_expire_days: 7,
    api_key_max_lifetime_days: 365,
    read_notification_retention_days: 90,
    audit_retention_days: 90,
    audit_legal_hold: false,
    geocoding_api_key_set: false,
    env_managed: {},
    step_up_fields: [],
    logs_viewer_enabled: true,
    ...overrides,
  })
}

/**
 * Mounts the form composable with the given session policy.
 *
 * @param overrides - The settings to change from the defaults.
 * @returns The form state.
 */
function mountForm(overrides: Partial<ServerSettingsDto>) {
  let form!: ReturnType<typeof useServerSettingsForm>
  const Host = defineComponent({
    setup() {
      form = useServerSettingsForm({ settings: makeSettings(overrides), templates: [] })
      return () => h('div')
    },
  })
  mount(Host, { global: { plugins: [i18n] } })
  return form
}

describe('session policy validation', () => {
  it('refuses an access token lifetime that is not shorter than the enforced idle timeout', () => {
    const form = mountForm({
      session_idle_timeout_enabled: true,
      session_idle_timeout_hours: 1,
      access_token_expire_minutes: 60,
    })

    expect(form.validateField('accessTokenExpireMinutes')).toBe(
      i18n.global.t('settings.server.session.accessNotBelowIdle'),
    )
  })

  it('accepts an access token lifetime shorter than the enforced idle timeout', () => {
    const form = mountForm({
      session_idle_timeout_enabled: true,
      session_idle_timeout_hours: 1,
      access_token_expire_minutes: 59,
    })

    expect(form.validateField('accessTokenExpireMinutes')).toBeNull()
  })

  it('does not limit the access token lifetime while the idle timeout is off', () => {
    const form = mountForm({
      session_idle_timeout_enabled: false,
      session_idle_timeout_hours: 1,
      access_token_expire_minutes: 1440,
    })

    expect(form.validateField('accessTokenExpireMinutes')).toBeNull()
  })
})
