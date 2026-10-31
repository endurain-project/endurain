import { beforeEach, describe, expect, it, vi } from 'vitest'

import type {
  MailSettingsDto,
  ServerSettingsDto,
  TileMapsTemplateDto,
} from '@/features/serverSettings/types'

import { apiFetch } from '@/services/http'
import {
  deleteLoginPhoto,
  fetchEmailStatus,
  fetchMailSettings,
  fetchServerSettings,
  fetchTileMapsTemplates,
  mapMailSettings,
  mapServerSettings,
  mapTileMapsTemplate,
  sendTestEmail,
  toMailSettingsWire,
  toServerSettingsWire,
  updateMailSettings,
  updateServerSettings,
  uploadLoginPhoto,
} from '@/features/serverSettings/services/serverSettings'

vi.mock('@/services/http', () => ({
  apiFetch: vi.fn<typeof apiFetch>(),
}))

/** Builds a full `ServerSettingsRead` wire payload, overridable per case. */
function makeSettingsDto(overrides: Partial<ServerSettingsDto> = {}): ServerSettingsDto {
  return {
    id: 1,
    version: 3,
    units: 'metric',
    currency: 'euro',
    num_records_per_page: 25,
    public_shareable_links: false,
    public_shareable_links_user_info: false,
    login_photo_set: true,
    signup_enabled: false,
    signup_require_admin_approval: true,
    signup_require_email_verification: true,
    sso_enabled: false,
    local_login_enabled: true,
    sso_auto_redirect: false,
    tileserver_url: 'https://tile.test/{z}/{x}/{y}.png',
    tileserver_attribution: '© Test',
    tileserver_api_key_set: true,
    tileserver_regenerate_thumbnails_on_change: false,
    map_background_color: '#dddddd',
    password_type: 'strict',
    password_length_regular_users: 8,
    password_length_admin_users: 12,
    geocoding_service: 'nominatim',
    geocoding_host: null,
    geocoding_use_https: true,
    geocoding_rate_limit: 1,
    session_idle_timeout_enabled: false,
    session_idle_timeout_hours: 1,
    session_absolute_timeout_hours: 24,
    access_token_expire_minutes: 15,
    refresh_token_expire_days: 7,
    read_notification_retention_days: 90,
    geocoding_api_key_set: false,
    env_managed: {},
    ...overrides,
  }
}

/** Builds a full `MailSettingsAdminRead` wire payload, overridable per case. */
function makeMailDto(overrides: Partial<MailSettingsDto> = {}): MailSettingsDto {
  return {
    id: 1,
    version: 2,
    host: 'mail.example.com',
    port: 587,
    security: 'starttls',
    username: 'me@example.com',
    from_address: null,
    password_set: true,
    env_managed: { host: 'SMTP_HOST' },
    ...overrides,
  }
}

/** Builds a full `TileMapsTemplate` wire payload, overridable per case. */
function makeTemplateDto(overrides: Partial<TileMapsTemplateDto> = {}): TileMapsTemplateDto {
  return {
    template_id: 'openstreetmap',
    name: 'OpenStreetMap',
    url_template: 'https://tile.openstreetmap.org/{z}/{x}/{y}.png',
    attribution: '© OpenStreetMap',
    map_background_color: '#aad3df',
    requires_api_key_frontend: false,
    requires_api_key_backend: false,
    ...overrides,
  }
}

describe('mapServerSettings', () => {
  it('maps the wire shape to the clean camel-cased model', () => {
    expect(mapServerSettings(makeSettingsDto())).toEqual({
      id: 1,
      version: 3,
      units: 'metric',
      currency: 'euro',
      numRecordsPerPage: 25,
      publicShareableLinks: false,
      publicShareableLinksUserInfo: false,
      loginPhotoSet: true,
      signupEnabled: false,
      signupRequireAdminApproval: true,
      signupRequireEmailVerification: true,
      ssoEnabled: false,
      localLoginEnabled: true,
      ssoAutoRedirect: false,
      tileserverUrl: 'https://tile.test/{z}/{x}/{y}.png',
      tileserverAttribution: '© Test',
      tileserverApiKeySet: true,
      tileserverRegenerateThumbnailsOnChange: false,
      mapBackgroundColor: '#dddddd',
      passwordType: 'strict',
      passwordLengthRegularUsers: 8,
      passwordLengthAdminUsers: 12,
      geocodingService: 'nominatim',
      geocodingHost: null,
      geocodingUseHttps: true,
      geocodingRateLimit: 1,
      sessionIdleTimeoutEnabled: false,
      sessionIdleTimeoutHours: 1,
      sessionAbsoluteTimeoutHours: 24,
      accessTokenExpireMinutes: 15,
      refreshTokenExpireDays: 7,
      readNotificationRetentionDays: 90,
      geocodingApiKeySet: false,
      envManaged: {},
    })
  })

  it('exposes only whether an API key is stored', () => {
    expect(mapServerSettings(makeSettingsDto()).tileserverApiKeySet).toBe(true)
    expect(mapServerSettings(makeSettingsDto()) as object).not.toHaveProperty('tileserverApiKey')
    expect(mapServerSettings(makeSettingsDto()) as object).not.toHaveProperty('geocodingApiKey')
    expect(
      mapServerSettings(makeSettingsDto({ geocoding_api_key_set: true })).geocodingApiKeySet,
    ).toBe(true)
  })

  it('carries the env-managed map', () => {
    const dto = makeSettingsDto({ env_managed: { geocoding_host: 'PHOTON_API_HOST' } })
    expect(mapServerSettings(dto).envManaged).toEqual({ geocoding_host: 'PHOTON_API_HOST' })
  })
})

describe('mapTileMapsTemplate', () => {
  it('maps the wire shape to the clean model', () => {
    expect(mapTileMapsTemplate(makeTemplateDto())).toEqual({
      templateId: 'openstreetmap',
      name: 'OpenStreetMap',
      urlTemplate: 'https://tile.openstreetmap.org/{z}/{x}/{y}.png',
      attribution: '© OpenStreetMap',
      mapBackgroundColor: '#aad3df',
      requiresApiKeyFrontend: false,
      requiresApiKeyBackend: false,
    })
  })
})

describe('toServerSettingsWire', () => {
  it('round-trips every editable field so the full record is replaced', () => {
    const settings = mapServerSettings(makeSettingsDto())
    const {
      id: _id,
      version: _version,
      login_photo_set: _loginPhotoSet,
      tileserver_api_key_set: _keySet,
      geocoding_api_key_set: _geoKeySet,
      env_managed: _envManaged,
      ...editable
    } = makeSettingsDto()
    expect(toServerSettingsWire(settings)).toEqual(editable)
  })

  it('omits the API key to keep it, and sends null to remove it', () => {
    const settings = mapServerSettings(makeSettingsDto())
    expect(toServerSettingsWire(settings)).not.toHaveProperty('tileserver_api_key')
    expect(toServerSettingsWire({ ...settings, tileserverApiKey: null })).toHaveProperty(
      'tileserver_api_key',
      null,
    )
    expect(toServerSettingsWire({ ...settings, tileserverApiKey: 'new-key' })).toHaveProperty(
      'tileserver_api_key',
      'new-key',
    )
  })

  it('omits the geocoding key to keep it, and sends null to remove it', () => {
    const settings = mapServerSettings(makeSettingsDto())
    expect(toServerSettingsWire(settings)).not.toHaveProperty('geocoding_api_key')
    expect(toServerSettingsWire({ ...settings, geocodingApiKey: null })).toHaveProperty(
      'geocoding_api_key',
      null,
    )
    expect(toServerSettingsWire({ ...settings, geocodingApiKey: 'geo-key' })).toHaveProperty(
      'geocoding_api_key',
      'geo-key',
    )
  })

  it('sends the session policy fields', () => {
    const wire = toServerSettingsWire(
      mapServerSettings(
        makeSettingsDto({ session_idle_timeout_enabled: true, access_token_expire_minutes: 30 }),
      ),
    )
    expect(wire).toMatchObject({
      session_idle_timeout_enabled: true,
      session_idle_timeout_hours: 1,
      session_absolute_timeout_hours: 24,
      access_token_expire_minutes: 30,
      refresh_token_expire_days: 7,
      read_notification_retention_days: 90,
    })
  })

  it('never sends the env-managed map or the key-stored flags', () => {
    const wire = toServerSettingsWire(mapServerSettings(makeSettingsDto()))
    expect(wire).not.toHaveProperty('env_managed')
    expect(wire).not.toHaveProperty('geocoding_api_key_set')
  })

  it('never sends the read-only id or login-photo flag', () => {
    const wire = toServerSettingsWire(mapServerSettings(makeSettingsDto()))
    expect(wire).not.toHaveProperty('id')
    expect(wire).not.toHaveProperty('login_photo_set')
  })
})

describe('server settings service requests', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('fetchServerSettings reads the admin endpoint and maps the response', async () => {
    vi.mocked(apiFetch).mockResolvedValue(makeSettingsDto())

    const settings = await fetchServerSettings()

    expect(apiFetch).toHaveBeenCalledWith('/server-settings', { signal: undefined })
    expect(settings.numRecordsPerPage).toBe(25)
  })

  it('fetchTileMapsTemplates maps the list and tolerates a null payload', async () => {
    vi.mocked(apiFetch).mockResolvedValueOnce([makeTemplateDto()])
    expect(await fetchTileMapsTemplates()).toHaveLength(1)
    expect(apiFetch).toHaveBeenCalledWith('/public/server-settings/tile-maps-templates', {
      signal: undefined,
    })

    vi.mocked(apiFetch).mockResolvedValueOnce(null)
    expect(await fetchTileMapsTemplates()).toEqual([])
  })

  it('updateServerSettings PUTs the full wire body', async () => {
    vi.mocked(apiFetch).mockResolvedValue(makeSettingsDto())
    const settings = mapServerSettings(makeSettingsDto({ signup_enabled: true }))

    await updateServerSettings(settings)

    expect(apiFetch).toHaveBeenCalledWith('/server-settings', {
      method: 'PUT',
      headers: { 'If-Match': '"3"' },
      body: JSON.stringify(toServerSettingsWire(settings)),
    })
  })

  it('uploadLoginPhoto posts the file as multipart form data and returns the photo version', async () => {
    let capturedBody: unknown
    vi.mocked(apiFetch).mockImplementation((_path, init) => {
      capturedBody = init?.body
      return Promise.resolve({ version: 4 })
    })
    const file = new File(['x'], 'login.png', { type: 'image/png' })

    await expect(uploadLoginPhoto(file)).resolves.toEqual({ version: 4 })

    expect(apiFetch).toHaveBeenCalledWith(
      '/server-settings/login-photo',
      expect.objectContaining({ method: 'POST' }),
    )
    expect(vi.mocked(apiFetch).mock.calls[0]?.[1]).not.toHaveProperty('responseType')
    expect(capturedBody).toBeInstanceOf(FormData)
    expect((capturedBody as FormData).get('file')).toBe(file)
  })

  it('deleteLoginPhoto issues a DELETE', async () => {
    vi.mocked(apiFetch).mockResolvedValue(undefined)

    await deleteLoginPhoto()

    expect(apiFetch).toHaveBeenCalledWith('/server-settings/login-photo', {
      method: 'DELETE',
      responseType: 'void',
    })
  })

  it('fetchEmailStatus reads the email status endpoint', async () => {
    vi.mocked(apiFetch).mockResolvedValue({ configured: false, problems: ['Host is not set'] })

    const status = await fetchEmailStatus()

    expect(apiFetch).toHaveBeenCalledWith('/server-settings/email', { signal: undefined })
    expect(status).toEqual({ configured: false, problems: ['Host is not set'] })
  })

  it('sendTestEmail POSTs to the test endpoint and expects no body', async () => {
    vi.mocked(apiFetch).mockResolvedValue(undefined)

    await sendTestEmail()

    expect(apiFetch).toHaveBeenCalledWith('/server-settings/email/test', {
      method: 'POST',
      responseType: 'void',
    })
  })
})

describe('mapMailSettings', () => {
  it('maps the wire shape to the clean camel-cased model', () => {
    expect(mapMailSettings(makeMailDto())).toEqual({
      version: 2,
      host: 'mail.example.com',
      port: 587,
      security: 'starttls',
      username: 'me@example.com',
      fromAddress: null,
      passwordSet: true,
      envManaged: { host: 'SMTP_HOST' },
    })
  })

  it('exposes only whether a password is stored', () => {
    expect(mapMailSettings(makeMailDto())).not.toHaveProperty('password')
  })
})

describe('toMailSettingsWire', () => {
  const update = {
    version: 2,
    host: 'mail.example.com',
    port: 465,
    security: 'ssl' as const,
    username: null,
    fromAddress: 'noreply@example.com',
  }

  it('sends every field so the full record is replaced', () => {
    expect(toMailSettingsWire(update)).toEqual({
      host: 'mail.example.com',
      port: 465,
      security: 'ssl',
      username: null,
      from_address: 'noreply@example.com',
    })
  })

  it('omits the password to keep it, and sends null to remove it', () => {
    expect(toMailSettingsWire(update)).not.toHaveProperty('password')
    expect(toMailSettingsWire({ ...update, password: null })).toHaveProperty('password', null)
    expect(toMailSettingsWire({ ...update, password: 'new-secret' })).toHaveProperty(
      'password',
      'new-secret',
    )
  })
})

describe('mail settings service requests', () => {
  beforeEach(() => {
    vi.mocked(apiFetch).mockReset()
  })

  it('fetchMailSettings reads the mail settings endpoint and maps the response', async () => {
    vi.mocked(apiFetch).mockResolvedValue(makeMailDto())

    const settings = await fetchMailSettings()

    expect(apiFetch).toHaveBeenCalledWith('/server-settings/email/settings', { signal: undefined })
    expect(settings.passwordSet).toBe(true)
  })

  it('updateMailSettings PUTs the wire body and maps the response', async () => {
    vi.mocked(apiFetch).mockResolvedValue(makeMailDto({ port: 465 }))

    const settings = await updateMailSettings({
      version: 2,
      host: 'mail.example.com',
      port: 465,
      security: 'ssl',
      username: null,
      fromAddress: null,
      password: 'new-secret',
    })

    expect(apiFetch).toHaveBeenCalledWith('/server-settings/email/settings', {
      method: 'PUT',
      headers: { 'If-Match': '"2"' },
      body: JSON.stringify({
        host: 'mail.example.com',
        port: 465,
        security: 'ssl',
        username: null,
        from_address: null,
        password: 'new-secret',
      }),
    })
    expect(settings.port).toBe(465)
  })
})
