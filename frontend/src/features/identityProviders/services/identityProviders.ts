import type {
  IdentityProvider,
  IdentityProviderCreateDto,
  IdentityProviderDto,
  IdentityProviderInput,
  IdentityProviderTemplate,
  IdentityProviderTemplateDto,
  IdentityProviderUpdateDto,
} from '@/features/identityProviders/types'

import { apiFetch } from '@/services/http'
import { ifMatchHeaders, rowVersion } from '@/services/ifMatch'

/**
 * Maps a raw `IdentityProvider` payload to the clean {@link IdentityProvider}
 * model — the single boundary where the backend wire format (snake_case) is
 * normalized so components never see the raw DTO.
 *
 * @param dto - Raw identity-provider payload from the backend.
 * @returns The normalized identity-provider model.
 */
export function mapIdentityProvider(dto: IdentityProviderDto): IdentityProvider {
  return {
    id: dto.id,
    version: rowVersion(dto.version),
    name: dto.name,
    slug: dto.slug,
    providerType: dto.provider_type,
    enabled: dto.enabled,
    issuerUrl: dto.issuer_url ?? null,
    clientId: dto.client_id ?? null,
    scopes: dto.scopes,
    icon: dto.icon ?? null,
    iconUploaded: dto.icon_uploaded ?? false,
    autoCreateUsers: dto.auto_create_users,
    syncUserInfo: dto.sync_user_info,
    authorizationEndpoint: dto.authorization_endpoint ?? null,
    tokenEndpoint: dto.token_endpoint ?? null,
    userinfoEndpoint: dto.userinfo_endpoint ?? null,
  }
}

/**
 * Maps a raw `IdentityProviderTemplate` payload to the clean model.
 *
 * @param dto - Raw preset payload from the backend.
 * @returns The normalized preset model.
 */
export function mapIdentityProviderTemplate(
  dto: IdentityProviderTemplateDto,
): IdentityProviderTemplate {
  return {
    templateId: dto.template_id,
    name: dto.name,
    providerType: dto.provider_type,
    issuerUrl: dto.issuer_url ?? null,
    scopes: dto.scopes,
    icon: dto.icon ?? null,
    description: dto.description,
    configurationNotes: dto.configuration_notes ?? null,
  }
}

/**
 * Projects a stored provider back onto the editable input shape, leaving the
 * client secret unset so it round-trips untouched. Used by the inline
 * enable/disable toggle, which re-sends the record with a flipped `enabled`.
 *
 * @param provider - The stored provider.
 * @returns The provider input with no client secret.
 */
export function toProviderInput(provider: IdentityProvider): IdentityProviderInput {
  return {
    name: provider.name,
    slug: provider.slug,
    providerType: provider.providerType,
    enabled: provider.enabled,
    issuerUrl: provider.issuerUrl,
    clientId: provider.clientId,
    clientSecret: null,
    scopes: provider.scopes,
    icon: provider.icon,
    autoCreateUsers: provider.autoCreateUsers,
    syncUserInfo: provider.syncUserInfo,
  }
}

/**
 * Builds the shared editable wire fields from a {@link IdentityProviderInput}.
 *
 * @param input - The clean provider input from the form.
 * @returns The snake-cased fields common to create and update.
 */
function toWireBase(input: IdentityProviderInput) {
  return {
    name: input.name,
    slug: input.slug,
    provider_type: input.providerType,
    enabled: input.enabled,
    issuer_url: input.issuerUrl,
    client_id: input.clientId,
    scopes: input.scopes,
    icon: input.icon,
    auto_create_users: input.autoCreateUsers,
    sync_user_info: input.syncUserInfo,
  }
}

/**
 * Fetches all configured identity providers (admin scope
 * `identity_providers:read`), including disabled ones.
 *
 * @param signal - Optional abort signal for cancellation.
 * @returns The providers, mapped to the clean model.
 * @throws {HttpError} When the request fails.
 */
export async function fetchIdentityProviders(signal?: AbortSignal): Promise<IdentityProvider[]> {
  const dtos = await apiFetch<IdentityProviderDto[] | null>('/identity-providers', { signal })
  return (dtos ?? []).map(mapIdentityProvider)
}

/**
 * Fetches the catalogue of provider presets (admin scope
 * `identity_providers:read`).
 *
 * @param signal - Optional abort signal for cancellation.
 * @returns The presets, mapped to the clean model.
 * @throws {HttpError} When the request fails.
 */
export async function fetchIdentityProviderTemplates(
  signal?: AbortSignal,
): Promise<IdentityProviderTemplate[]> {
  const dtos = await apiFetch<IdentityProviderTemplateDto[] | null>(
    '/identity-providers/templates',
    { signal },
  )
  return (dtos ?? []).map(mapIdentityProviderTemplate)
}

/**
 * Creates an identity provider (admin scope `identity_providers:write`). The
 * client secret is required here; the backend returns `409` on a duplicate slug.
 *
 * @param input - The clean provider input.
 * @returns The created provider, mapped to the clean model.
 * @throws {HttpError} When the request fails (e.g. duplicate slug).
 */
export async function createIdentityProvider(
  input: IdentityProviderInput,
): Promise<IdentityProvider> {
  const payload: IdentityProviderCreateDto = {
    ...toWireBase(input),
    client_secret: input.clientSecret ?? '',
  }
  const dto = await apiFetch<IdentityProviderDto>('/identity-providers', {
    method: 'POST',
    body: JSON.stringify(payload),
  })
  return mapIdentityProvider(dto)
}

/**
 * Updates an identity provider (admin scope `identity_providers:write`). The
 * client secret is sent only when the admin entered a new one, so leaving the
 * field blank keeps the stored secret.
 *
 * @param id - The provider id.
 * @param input - The clean provider input.
 * @param version - The provider version read by the editor.
 * @returns The updated provider, mapped to the clean model.
 * @throws {HttpError} When the request fails (e.g. duplicate slug, not found).
 */
export async function updateIdentityProvider(
  id: number,
  input: IdentityProviderInput,
  version: number,
): Promise<IdentityProvider> {
  const payload: IdentityProviderUpdateDto = { ...toWireBase(input) }
  if (input.clientSecret) {
    payload.client_secret = input.clientSecret
  }
  const dto = await apiFetch<IdentityProviderDto>(`/identity-providers/${id}`, {
    method: 'PUT',
    headers: ifMatchHeaders(version),
    body: JSON.stringify(payload),
  })
  return mapIdentityProvider(dto)
}

/**
 * Deletes an identity provider (admin scope `identity_providers:write`). The
 * backend returns `409` when users are still linked to the provider.
 *
 * @param id - The provider id.
 * @param version - The provider version the list item was read at, for `If-Match`.
 * @throws {HttpError} When the request fails (e.g. users still linked, or `412` when stale).
 */
export async function deleteIdentityProvider(id: number, version: number): Promise<void> {
  await apiFetch(`/identity-providers/${id}`, {
    method: 'DELETE',
    headers: ifMatchHeaders(version),
    responseType: 'void',
  })
}

/**
 * Uploads the image a provider shows on the login screen (admin scope
 * `identity_providers:write`). The file is sent as multipart form data under the
 * `file` field; the backend validates it and stores it under a server-generated
 * key, so the caller's filename is never used. The upload replaces any custom
 * icon URL until it is removed.
 *
 * @param id - The provider id.
 * @param file - The PNG, JPEG, GIF or WebP image.
 * @throws {HttpError} When the upload fails (e.g. wrong file type or too large).
 */
export async function uploadIdentityProviderIcon(id: number, file: File): Promise<void> {
  const formData = new FormData()
  formData.append('file', file)
  await apiFetch(`/identity-providers/${id}/icon`, {
    method: 'POST',
    body: formData,
    responseType: 'void',
  })
}

/**
 * Removes a provider's uploaded icon (admin scope `identity_providers:write`).
 *
 * @param id - The provider id.
 * @throws {HttpError} When the deletion fails.
 */
export async function deleteIdentityProviderIcon(id: number): Promise<void> {
  await apiFetch(`/identity-providers/${id}/icon`, {
    method: 'DELETE',
    responseType: 'void',
  })
}
