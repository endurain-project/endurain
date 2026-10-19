import { beforeEach, describe, expect, it, vi } from 'vitest'

import type { ServerSettingsDto, TileMapsTemplateDto } from '@/features/serverSettings/types'

import { apiFetch } from '@/services/http'
import {
  deleteLoginPhoto,
  fetchEmailStatus,
  fetchServerSettings,
  fetchTileMapsTemplates,
  mapServerSettings,
  mapTileMapsTemplate,
  sendTestEmail,
  toServerSettingsWire,
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
    tileserver_api_key: 'secret-key',
    tileserver_regenerate_thumbnails_on_change: false,
    map_background_color: '#dddddd',
    password_type: 'strict',
    password_length_regular_users: 8,
    password_length_admin_users: 12,
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
      tileserverApiKey: 'secret-key',
      tileserverRegenerateThumbnailsOnChange: false,
      mapBackgroundColor: '#dddddd',
      passwordType: 'strict',
      passwordLengthRegularUsers: 8,
      passwordLengthAdminUsers: 12,
    })
  })

  it('normalizes a missing API key to null', () => {
    expect(
      mapServerSettings(makeSettingsDto({ tileserver_api_key: null })).tileserverApiKey,
    ).toBeNull()
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
  it('round-trips every field so the full record is replaced', () => {
    const settings = mapServerSettings(makeSettingsDto())
    expect(toServerSettingsWire(settings)).toEqual(makeSettingsDto())
  })
})

describe('server settings service requests', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('fetchServerSettings reads the admin endpoint and maps the response', async () => {
    vi.mocked(apiFetch).mockResolvedValue(makeSettingsDto())

    const settings = await fetchServerSettings()

    expect(apiFetch).toHaveBeenCalledWith('/server_settings', { signal: undefined })
    expect(settings.numRecordsPerPage).toBe(25)
  })

  it('fetchTileMapsTemplates maps the list and tolerates a null payload', async () => {
    vi.mocked(apiFetch).mockResolvedValueOnce([makeTemplateDto()])
    expect(await fetchTileMapsTemplates()).toHaveLength(1)
    expect(apiFetch).toHaveBeenCalledWith('/server_settings/tile_maps_templates', {
      signal: undefined,
    })

    vi.mocked(apiFetch).mockResolvedValueOnce(null)
    expect(await fetchTileMapsTemplates()).toEqual([])
  })

  it('updateServerSettings PUTs the full wire body', async () => {
    vi.mocked(apiFetch).mockResolvedValue(makeSettingsDto())
    const settings = mapServerSettings(makeSettingsDto({ signup_enabled: true }))

    await updateServerSettings(settings)

    expect(apiFetch).toHaveBeenCalledWith('/server_settings', {
      method: 'PUT',
      body: JSON.stringify(toServerSettingsWire(settings)),
    })
  })

  it('uploadLoginPhoto posts the file as multipart form data', async () => {
    let capturedBody: unknown
    vi.mocked(apiFetch).mockImplementation((_path, init) => {
      capturedBody = init?.body
      return Promise.resolve(undefined)
    })
    const file = new File(['x'], 'login.png', { type: 'image/png' })

    await uploadLoginPhoto(file)

    expect(apiFetch).toHaveBeenCalledWith(
      '/server_settings/upload/login',
      expect.objectContaining({ method: 'POST', responseType: 'void' }),
    )
    expect(capturedBody).toBeInstanceOf(FormData)
    expect((capturedBody as FormData).get('file')).toBe(file)
  })

  it('deleteLoginPhoto issues a DELETE', async () => {
    vi.mocked(apiFetch).mockResolvedValue(undefined)

    await deleteLoginPhoto()

    expect(apiFetch).toHaveBeenCalledWith('/server_settings/upload/login', {
      method: 'DELETE',
      responseType: 'void',
    })
  })

  it('fetchEmailStatus reads the email status endpoint', async () => {
    vi.mocked(apiFetch).mockResolvedValue({ configured: false, problems: ['SMTP_HOST is not set'] })

    const status = await fetchEmailStatus()

    expect(apiFetch).toHaveBeenCalledWith('/server_settings/email', { signal: undefined })
    expect(status).toEqual({ configured: false, problems: ['SMTP_HOST is not set'] })
  })

  it('sendTestEmail POSTs to the test endpoint and returns the confirmation message', async () => {
    vi.mocked(apiFetch).mockResolvedValue({ message: 'Test email sent to admin@example.com.' })

    const message = await sendTestEmail()

    expect(apiFetch).toHaveBeenCalledWith('/server_settings/email/test', { method: 'POST' })
    expect(message).toBe('Test email sent to admin@example.com.')
  })
})
