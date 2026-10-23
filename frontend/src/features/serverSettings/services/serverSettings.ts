import type {
  EmailStatusDto,
  LogFilters,
  LogPage,
  LogsStatusDto,
  MailSettings,
  MailSettingsDto,
  MailSettingsEditDto,
  MailSettingsUpdate,
  ServerSettings,
  ServerSettingsDto,
  ServerSettingsEditDto,
  ServerSettingsUpdate,
  TileMapsTemplate,
  TileMapsTemplateDto,
} from '@/features/serverSettings/types'

import { apiFetch } from '@/services/http'

/**
 * Maps a raw `ServerSettingsAdminRead` payload to the clean {@link ServerSettings}
 * model — the single boundary where the backend wire format (snake_case) is
 * normalized so components never see the raw DTO.
 *
 * @param dto - Raw server-settings payload from the backend.
 * @returns The normalized server-settings model.
 */
export function mapServerSettings(dto: ServerSettingsDto): ServerSettings {
  return {
    id: dto.id,
    version: dto.version,
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
    tileserverApiKeySet: dto.tileserver_api_key_set,
    tileserverRegenerateThumbnailsOnChange: dto.tileserver_regenerate_thumbnails_on_change,
    mapBackgroundColor: dto.map_background_color,
    passwordType: dto.password_type,
    passwordLengthRegularUsers: dto.password_length_regular_users,
    passwordLengthAdminUsers: dto.password_length_admin_users,
    geocodingService: dto.geocoding_service,
    geocodingHost: dto.geocoding_host,
    geocodingUseHttps: dto.geocoding_use_https,
    geocodingRateLimit: dto.geocoding_rate_limit,
    sessionIdleTimeoutEnabled: dto.session_idle_timeout_enabled,
    sessionIdleTimeoutHours: dto.session_idle_timeout_hours,
    sessionAbsoluteTimeoutHours: dto.session_absolute_timeout_hours,
    accessTokenExpireMinutes: dto.access_token_expire_minutes,
    refreshTokenExpireDays: dto.refresh_token_expire_days,
    readNotificationRetentionDays: dto.read_notification_retention_days,
    geocodingApiKeySet: dto.geocoding_api_key_set,
    envManaged: dto.env_managed,
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
 * editable column is sent because the edit endpoint forbids extra fields and
 * replaces the whole record, so unedited fields must round-trip untouched. The
 * row id and the login-photo flag are read-only: the photo routes own the flag. Deriving the
 * return type from the generated schema turns a missing field into a compile
 * error instead of a runtime `422`.
 *
 * @param settings - The server settings (already merged with any edits).
 * @returns The snake-cased editable body; it carries an API key only when one is being set or removed.
 */
export function toServerSettingsWire(settings: ServerSettingsUpdate): ServerSettingsEditDto {
  return {
    units: settings.units,
    currency: settings.currency,
    num_records_per_page: settings.numRecordsPerPage,
    public_shareable_links: settings.publicShareableLinks,
    public_shareable_links_user_info: settings.publicShareableLinksUserInfo,
    signup_enabled: settings.signupEnabled,
    signup_require_admin_approval: settings.signupRequireAdminApproval,
    signup_require_email_verification: settings.signupRequireEmailVerification,
    sso_enabled: settings.ssoEnabled,
    local_login_enabled: settings.localLoginEnabled,
    sso_auto_redirect: settings.ssoAutoRedirect,
    tileserver_url: settings.tileserverUrl,
    tileserver_attribution: settings.tileserverAttribution,
    tileserver_regenerate_thumbnails_on_change: settings.tileserverRegenerateThumbnailsOnChange,
    map_background_color: settings.mapBackgroundColor,
    password_type: settings.passwordType,
    password_length_regular_users: settings.passwordLengthRegularUsers,
    password_length_admin_users: settings.passwordLengthAdminUsers,
    geocoding_service: settings.geocodingService,
    geocoding_host: settings.geocodingHost,
    geocoding_use_https: settings.geocodingUseHttps,
    geocoding_rate_limit: settings.geocodingRateLimit,
    session_idle_timeout_enabled: settings.sessionIdleTimeoutEnabled,
    session_idle_timeout_hours: settings.sessionIdleTimeoutHours,
    session_absolute_timeout_hours: settings.sessionAbsoluteTimeoutHours,
    access_token_expire_minutes: settings.accessTokenExpireMinutes,
    refresh_token_expire_days: settings.refreshTokenExpireDays,
    read_notification_retention_days: settings.readNotificationRetentionDays,
    // Omitted keeps the stored key; the backend never returns it, so it cannot round-trip.
    ...(settings.tileserverApiKey !== undefined && {
      tileserver_api_key: settings.tileserverApiKey,
    }),
    ...(settings.geocodingApiKey !== undefined && {
      geocoding_api_key: settings.geocodingApiKey,
    }),
  }
}

/**
 * Fetches the full server settings (admin scope `server_settings:read`). The
 * tile-server API key is never returned, only whether one is stored.
 *
 * @param signal - Optional abort signal for cancellation.
 * @returns The server settings, mapped to the clean model.
 * @throws {HttpError} When the request fails.
 */
export async function fetchServerSettings(signal?: AbortSignal): Promise<ServerSettings> {
  const dto = await apiFetch<ServerSettingsDto>('/server-settings', { signal })
  return mapServerSettings(dto)
}

/**
 * Fetches the available tile-server presets (public endpoint).
 *
 * @param signal - Optional abort signal for cancellation.
 * @returns The tile-map presets, mapped to the clean model.
 * @throws {HttpError} When the request fails.
 */
export async function fetchTileMapsTemplates(signal?: AbortSignal): Promise<TileMapsTemplate[]> {
  const dtos = await apiFetch<TileMapsTemplateDto[] | null>(
    '/public/server-settings/tile-maps-templates',
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
 * @throws {HttpError} When the request fails (e.g. invalid tile-server URL), including 412 when the copy is stale.
 */
export async function updateServerSettings(
  settings: ServerSettingsUpdate,
): Promise<ServerSettings> {
  const dto = await apiFetch<ServerSettingsDto>('/server-settings', {
    method: 'PUT',
    headers: { 'If-Match': `"${settings.version}"` },
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
  await apiFetch('/server-settings/login-photo', {
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
  await apiFetch('/server-settings/login-photo', {
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
  return apiFetch<EmailStatusDto>('/server-settings/email', { signal })
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
  const result = await apiFetch<{ message: string }>('/server-settings/email/test', {
    method: 'POST',
  })
  return result.message
}

/**
 * Maps a raw `MailSettingsAdminRead` payload to the clean {@link MailSettings} model.
 *
 * @param dto - Raw mail-settings payload from the backend.
 * @returns The normalized mail-settings model.
 */
export function mapMailSettings(dto: MailSettingsDto): MailSettings {
  return {
    version: dto.version,
    host: dto.host,
    port: dto.port,
    security: dto.security,
    username: dto.username,
    fromAddress: dto.from_address,
    passwordSet: dto.password_set,
    envManaged: dto.env_managed,
  }
}

/**
 * Rebuilds the full editable wire payload from a {@link MailSettingsUpdate}. Every
 * field is sent because the edit endpoint forbids extra fields and replaces the
 * whole record; only the password may be left out. Deriving the return type from
 * the generated schema turns a missing field into a compile error.
 *
 * @param settings - The mail settings to persist.
 * @returns The snake-cased editable body; it carries the password only when one is being set or removed.
 */
export function toMailSettingsWire(settings: MailSettingsUpdate): MailSettingsEditDto {
  return {
    host: settings.host,
    port: settings.port,
    security: settings.security,
    username: settings.username,
    from_address: settings.fromAddress,
    // Omitted keeps the stored password; the backend never returns it, so it cannot round-trip.
    ...(settings.password !== undefined && { password: settings.password }),
  }
}

/**
 * Fetches the mail server settings (admin scope `server_settings:read`). The
 * password is never returned, only whether one is stored.
 *
 * @param signal - Optional abort signal for cancellation.
 * @returns The mail settings, mapped to the clean model.
 * @throws {HttpError} When the request fails.
 */
export async function fetchMailSettings(signal?: AbortSignal): Promise<MailSettings> {
  const dto = await apiFetch<MailSettingsDto>('/server-settings/email/settings', { signal })
  return mapMailSettings(dto)
}

/**
 * Updates the mail server settings (admin scope `server_settings:write`). The
 * backend validates the configuration and rejects a change to a field an
 * environment variable currently sets.
 *
 * @param settings - The mail settings to persist.
 * @returns The updated mail settings, mapped to the clean model.
 * @throws {HttpError} `400` when the configuration is not usable or a field is env-managed, `412` when the copy is stale.
 */
export async function updateMailSettings(settings: MailSettingsUpdate): Promise<MailSettings> {
  const dto = await apiFetch<MailSettingsDto>('/server-settings/email/settings', {
    method: 'PUT',
    headers: { 'If-Match': `"${settings.version}"` },
    body: JSON.stringify(toMailSettingsWire(settings)),
  })
  return mapMailSettings(dto)
}

/**
 * Fetches whether the server-log viewer is available (admin scope
 * `server_settings:logs`). It is off for the demo and for deployments that run
 * more than one process.
 *
 * @param signal - Optional abort signal for cancellation.
 * @returns The viewer status.
 * @throws {HttpError} When the request fails.
 */
export async function fetchLogsStatus(signal?: AbortSignal): Promise<LogsStatusDto> {
  return apiFetch<LogsStatusDto>('/server-settings/logs/status', { signal })
}

/**
 * Fetches records from the end of the server log (admin scope `server_settings:logs`).
 *
 * @param filters - Severity and text filters.
 * @param after - Cursor from an earlier page to read only newer records, or null for the newest.
 * @param signal - Optional abort signal for cancellation.
 * @returns The matching records, oldest first, and the next cursor.
 * @throws {HttpError} When the request fails (404 when the viewer is unavailable).
 */
export async function fetchLogs(
  filters: LogFilters,
  after: number | null,
  signal?: AbortSignal,
): Promise<LogPage> {
  const params = new URLSearchParams()
  if (filters.level) {
    params.set('level', filters.level)
  }
  if (filters.search) {
    params.set('search', filters.search)
  }
  if (after !== null) {
    params.set('after', String(after))
  }
  return apiFetch<LogPage>(`/server-settings/logs?${params}`, { signal })
}

/**
 * Downloads the current server log file (admin scope `server_settings:logs`).
 *
 * @param signal - Optional abort signal for cancellation.
 * @returns The log file as a {@link Blob}.
 * @throws {HttpError} When the request fails.
 */
export async function downloadLogs(signal?: AbortSignal): Promise<Blob> {
  return apiFetch<Blob>('/server-settings/logs/download', {
    responseType: 'blob',
    timeoutMs: 0,
    signal,
  })
}

/**
 * Empties the server log and deletes its rotated backups (admin scope
 * `server_settings:logs_clear`). The backend records the action in the new log.
 *
 * @throws {HttpError} When the request fails.
 */
export async function clearLogs(): Promise<void> {
  await apiFetch('/server-settings/logs', { method: 'DELETE', responseType: 'void' })
}
