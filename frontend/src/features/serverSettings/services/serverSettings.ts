import type {
  EmailStatusDto,
  ServerSettings,
  ServerSettingsDto,
  ServerSettingsEditDto,
  TileMapsTemplate,
  TileMapsTemplateDto,
} from '@/features/serverSettings/types'

import { apiFetch } from '@/services/http'

/**
 * Maps a raw `ServerSettingsRead` payload to the clean {@link ServerSettings}
 * model — the single boundary where the backend wire format (snake_case) is
 * normalized so components never see the raw DTO.
 *
 * @param dto - Raw server-settings payload from the backend.
 * @returns The normalized server-settings model.
 */
export function mapServerSettings(dto: ServerSettingsDto): ServerSettings {
  return {
    id: dto.id,
    units: dto.units,
    currency: dto.currency,
    numRecordsPerPage: dto.num_records_per_page,
    publicShareableLinks: dto.public_shareable_links,
    publicShareableLinksUserInfo: dto.public_shareable_links_user_info,
    loginPhotoSet: dto.login_photo_set,
    signupEnabled: dto.signup_enabled,
    signupRequireAdminApproval: dto.signup_require_admin_approval,
    signupRequireEmailVerification: dto.signup_require_email_verification,
    ssoEnabled: dto.sso_enabled,
    localLoginEnabled: dto.local_login_enabled,
    ssoAutoRedirect: dto.sso_auto_redirect,
    tileserverUrl: dto.tileserver_url,
    tileserverAttribution: dto.tileserver_attribution,
    tileserverApiKey: dto.tileserver_api_key ?? null,
    tileserverRegenerateThumbnailsOnChange: dto.tileserver_regenerate_thumbnails_on_change,
    mapBackgroundColor: dto.map_background_color,
    passwordType: dto.password_type,
    passwordLengthRegularUsers: dto.password_length_regular_users,
    passwordLengthAdminUsers: dto.password_length_admin_users,
  }
}

/**
 * Maps a raw `TileMapsTemplate` payload to the clean {@link TileMapsTemplate}.
 *
 * @param dto - Raw tile-map template payload from the backend.
 * @returns The normalized template model.
 */
export function mapTileMapsTemplate(dto: TileMapsTemplateDto): TileMapsTemplate {
  return {
    templateId: dto.template_id,
    name: dto.name,
    urlTemplate: dto.url_template,
    attribution: dto.attribution,
    mapBackgroundColor: dto.map_background_color,
    requiresApiKeyFrontend: dto.requires_api_key_frontend,
    requiresApiKeyBackend: dto.requires_api_key_backend,
  }
}

/**
 * Rebuilds the full editable wire payload from a {@link ServerSettings}. Every
 * column is sent because the edit endpoint forbids extra fields and replaces
 * the whole record, so unedited fields must round-trip untouched. Deriving the
 * return type from the generated schema turns a missing field into a compile
 * error instead of a runtime `422`.
 *
 * @param settings - The server settings (already merged with any edits).
 * @returns The snake-cased editable body.
 */
export function toServerSettingsWire(settings: ServerSettings): ServerSettingsEditDto {
  return {
    id: settings.id,
    units: settings.units,
    currency: settings.currency,
    num_records_per_page: settings.numRecordsPerPage,
    public_shareable_links: settings.publicShareableLinks,
    public_shareable_links_user_info: settings.publicShareableLinksUserInfo,
    login_photo_set: settings.loginPhotoSet,
    signup_enabled: settings.signupEnabled,
    signup_require_admin_approval: settings.signupRequireAdminApproval,
    signup_require_email_verification: settings.signupRequireEmailVerification,
    sso_enabled: settings.ssoEnabled,
    local_login_enabled: settings.localLoginEnabled,
    sso_auto_redirect: settings.ssoAutoRedirect,
    tileserver_url: settings.tileserverUrl,
    tileserver_attribution: settings.tileserverAttribution,
    tileserver_api_key: settings.tileserverApiKey,
    tileserver_regenerate_thumbnails_on_change: settings.tileserverRegenerateThumbnailsOnChange,
    map_background_color: settings.mapBackgroundColor,
    password_type: settings.passwordType,
    password_length_regular_users: settings.passwordLengthRegularUsers,
    password_length_admin_users: settings.passwordLengthAdminUsers,
  }
}

/**
 * Fetches the full server settings (admin scope `server_settings:read`). The
 * backend returns the decrypted tile-server API key for admins.
 *
 * @param signal - Optional abort signal for cancellation.
 * @returns The server settings, mapped to the clean model.
 * @throws {HttpError} When the request fails.
 */
export async function fetchServerSettings(signal?: AbortSignal): Promise<ServerSettings> {
  const dto = await apiFetch<ServerSettingsDto>('/server_settings', { signal })
  return mapServerSettings(dto)
}

/**
 * Fetches the available tile-server presets (admin scope `server_settings:read`).
 *
 * @param signal - Optional abort signal for cancellation.
 * @returns The tile-map presets, mapped to the clean model.
 * @throws {HttpError} When the request fails.
 */
export async function fetchTileMapsTemplates(signal?: AbortSignal): Promise<TileMapsTemplate[]> {
  const dtos = await apiFetch<TileMapsTemplateDto[] | null>(
    '/server_settings/tile_maps_templates',
    {
      signal,
    },
  )
  return (dtos ?? []).map(mapTileMapsTemplate)
}

/**
 * Updates the server settings (admin scope `server_settings:write`). The whole
 * record is sent; the backend validates the tile-server URL and may reject the
 * change with a `422`.
 *
 * @param settings - The full settings to persist.
 * @returns The updated server settings, mapped to the clean model.
 * @throws {HttpError} When the request fails (e.g. invalid tile-server URL).
 */
export async function updateServerSettings(settings: ServerSettings): Promise<ServerSettings> {
  const dto = await apiFetch<ServerSettingsDto>('/server_settings', {
    method: 'PUT',
    body: JSON.stringify(toServerSettingsWire(settings)),
  })
  return mapServerSettings(dto)
}

/**
 * Uploads a custom login-screen photo (admin scope `server_settings:write`).
 * The file is sent as multipart form data under the `file` field; the backend
 * validates it (PNG image) and stores it under a server-generated name, so the
 * caller's filename is never used to build a path.
 *
 * @param file - The PNG image to upload.
 * @throws {HttpError} When the upload fails (e.g. wrong file type).
 */
export async function uploadLoginPhoto(file: File): Promise<void> {
  const formData = new FormData()
  formData.append('file', file)
  await apiFetch('/server_settings/upload/login', {
    method: 'POST',
    body: formData,
    responseType: 'void',
  })
}

/**
 * Removes the custom login-screen photo (admin scope `server_settings:write`).
 *
 * @throws {HttpError} When the deletion fails.
 */
export async function deleteLoginPhoto(): Promise<void> {
  await apiFetch('/server_settings/upload/login', {
    method: 'DELETE',
    responseType: 'void',
  })
}

/**
 * Fetches whether outgoing email is usable (admin scope `server_settings:read`).
 * When it is not, `problems` lists the invalid settings by name (never by value).
 *
 * @param signal - Optional abort signal for cancellation.
 * @returns The email status.
 * @throws {HttpError} When the request fails.
 */
export async function fetchEmailStatus(signal?: AbortSignal): Promise<EmailStatusDto> {
  return apiFetch<EmailStatusDto>('/server_settings/email', { signal })
}

/**
 * Sends a test email to the calling admin's own address (admin scope
 * `server_settings:write`). The send is synchronous, so a failure surfaces the
 * mail server's failure category and SMTP status code in the error detail.
 *
 * @returns The confirmation message naming the recipient.
 * @throws {HttpError} `503` when email is not configured, `502` when the mail
 *   server did not accept the message.
 */
export async function sendTestEmail(): Promise<string> {
  const result = await apiFetch<{ message: string }>('/server_settings/email/test', {
    method: 'POST',
  })
  return result.message
}
