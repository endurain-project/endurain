import type {
  CreateUserInput,
  EditUserFields,
  ManagedUser,
  UserDeletionStatus,
  UserDto,
  UserEditDto,
  UsersListParams,
  UsersListResponseDto,
  UsersPage,
} from '@/features/users/types'
import type { StepUpInput, StepUpRequestDto } from '@/features/security/types'
import type { Schemas } from '@/types'

import { resolveAvatarUrl } from '@/features/auth/services/mappers'
import { apiFetch } from '@/services/http'
import { ifMatchHeaders, rowVersion } from '@/services/ifMatch'
import { toStepUpWire } from '@/features/security/services/security'

/**
 * Maps a raw `UserRead` payload to the clean {@link ManagedUser} model — the
 * single boundary where the backend wire format (snake_case, optional-with-
 * defaults fields) is normalized so components never see the raw DTO.
 *
 * @param dto - Raw user payload from the backend.
 * @returns The normalized managed-user model.
 */
export function mapManagedUser(dto: UserDto): ManagedUser {
  return {
    id: dto.id,
    version: rowVersion(dto.version),
    name: dto.name,
    username: dto.username,
    email: dto.email,
    accessType: dto.access_type,
    active: dto.active,
    emailVerified: dto.email_verified ?? false,
    pendingEmail: dto.pending_email ?? null,
    pendingEmailExpiresAt: dto.pending_email_expires_at ?? null,
    deletionRequestedAt: dto.deletion_requested_at ?? null,
    pendingAdminApproval: dto.pending_admin_approval ?? false,
    mfaEnabled: dto.mfa_enabled ?? false,
    externalAuthCount: dto.external_auth_count ?? 0,
    preferredLanguage: dto.preferred_language ?? 'en',
    gender: dto.gender ?? 'unspecified',
    units: dto.units ?? 'metric',
    weightUnits: dto.weight_units ?? null,
    currency: dto.currency ?? 'euro',
    firstDayOfWeek: dto.first_day_of_week ?? 'monday',
    city: dto.city ?? null,
    birthdate: dto.birthdate ?? null,
    height: dto.height ?? null,
    maxHeartRate: dto.max_heart_rate ?? null,
    photoPath: dto.photo_path ?? null,
    avatarUrl: resolveAvatarUrl(dto.photo_path),
  }
}

/**
 * Rebuilds the `UserEdit` wire payload from a {@link ManagedUser}.
 * Every stored column is sent so fields the admin form doesn't expose round-trip
 * untouched, but the derived, read-only fields are omitted: `id` is the path,
 * `mfa_enabled`, `pending_admin_approval` and `external_auth_count` are not editable, and the edit body rejects them.
 *
 * @param user - The managed user (already merged with any edits).
 * @returns The snake-cased editable body (without the read-only fields).
 */
function toUserWire(user: ManagedUser): UserEditDto {
  return {
    name: user.name,
    username: user.username,
    email: user.email,
    access_type: user.accessType,
    active: user.active,
    email_verified: user.emailVerified,
    preferred_language: user.preferredLanguage,
    gender: user.gender,
    units: user.units,
    weight_units: user.weightUnits,
    currency: user.currency,
    first_day_of_week: user.firstDayOfWeek,
    city: user.city,
    birthdate: user.birthdate,
    height: user.height,
    max_heart_rate: user.maxHeartRate,
    // photo_path is not sent: the photo is owned by the upload and delete endpoints,
    // and the backend refuses it on write.
  }
}

/**
 * Fetches one page of all users (admin scope `users:read-all`).
 *
 * @param params - Page number, size, the five list filters and an optional username search.
 * @param signal - Optional abort signal for cancellation.
 * @returns The page's users (mapped) plus the total record count.
 * @throws {HttpError} When the request fails.
 */
export async function fetchUsers(
  {
    page,
    numRecords,
    showInactive,
    showEmailUnverified,
    showPendingApproval,
    showExternalAuth,
    showLocalAuth,
    username,
  }: UsersListParams,
  signal?: AbortSignal,
): Promise<UsersPage> {
  // A `show*` flag that is `true` adds no filter; one that is `false` asks the server for the
  // users outside that category (`active=true`, `external_auth=false`, ...).
  if (!showExternalAuth && !showLocalAuth) {
    return { records: [], total: 0 }
  }
  const params = new URLSearchParams({
    page_number: String(page),
    num_records: String(numRecords),
  })
  if (!showInactive) {
    params.set('active', 'true')
  }
  if (!showEmailUnverified) {
    params.set('email_verified', 'true')
  }
  if (!showPendingApproval) {
    params.set('pending_approval', 'false')
  }
  // The two switches are one tri-state filter: both on adds none, one off keeps the other kind.
  if (showExternalAuth !== showLocalAuth) {
    params.set('external_auth', String(showExternalAuth))
  }
  if (username) {
    params.set('username_contains', username)
  }
  const response = await apiFetch<UsersListResponseDto>(`/users?${params.toString()}`, { signal })
  return {
    records: response.items.map(mapManagedUser),
    total: response.total,
  }
}

/**
 * Creates a user (admin scope `users:write`). The admin supplies the full
 * profile and access fields via the form; only MFA and the photo are seeded
 * here (MFA off, no photo) — the user can enrol MFA and upload a photo later.
 *
 * Creating an administrator carries the creating administrator's own step-up; any other account sends none.
 *
 * @param input - The clean create input.
 * @param stepUp - The administrator's step-up, for the creation of an administrator.
 * @returns The created user, mapped to the clean model.
 * @throws {HttpError} When the request fails (e.g. duplicate username/email, or a refused step-up).
 */
export async function createUser(
  input: CreateUserInput,
  stepUp: StepUpInput | null = null,
): Promise<ManagedUser> {
  const payload: Schemas['UserAdminCreate'] = {
    name: input.name,
    username: input.username,
    email: input.email,
    password: input.password,
    access_type: input.accessType,
    active: input.active,
    email_verified: input.emailVerified,
    units: input.units,
    weight_units: input.weightUnits,
    currency: input.currency,
    preferred_language: input.preferredLanguage,
    gender: input.gender,
    first_day_of_week: input.firstDayOfWeek,
    city: input.city,
    birthdate: input.birthdate,
    height: input.height,
    max_heart_rate: input.maxHeartRate,
    ...(stepUp ? { step_up: toStepUpWire(stepUp) } : {}),
  }
  const dto = await apiFetch<UserDto>('/users', {
    method: 'POST',
    body: JSON.stringify(payload),
  })
  return mapManagedUser(dto)
}

/**
 * Updates a user's admin-editable fields (scope `users:write`). The edits are
 * merged onto the existing record and the editable columns are sent; the
 * derived read-only fields (`mfa_enabled`, `external_auth_count`) are omitted
 * because the edit body rejects them.
 * An edit that changes the email, access type or active flag carries the
 * administrator's own step-up; any other edit sends none.
 *
 * @param user - The existing managed user.
 * @param edits - The admin-editable field values.
 * @param stepUp - The administrator's step-up, for an edit of email, access type or active flag.
 * @returns The updated user, mapped to the clean model.
 * @throws {HttpError} When the request fails (e.g. duplicate username/email, or a refused step-up).
 */
export async function updateUser(
  user: ManagedUser,
  edits: EditUserFields,
  stepUp: StepUpInput | null = null,
): Promise<ManagedUser> {
  const merged: ManagedUser = { ...user, ...edits }
  const wire = toUserWire(merged)
  const dto = await apiFetch<UserDto>(`/users/${user.id}`, {
    method: 'PATCH',
    headers: ifMatchHeaders(user.version),
    body: JSON.stringify(stepUp ? { ...wire, step_up: toStepUpWire(stepUp) } : wire),
  })
  return mapManagedUser(dto)
}

/**
 * Fetches a single user by id (admin scope `users:read-all`).
 *
 * @param id - The user id.
 * @param signal - Optional abort signal for cancellation.
 * @returns The user mapped to the clean model, or `null` when not found.
 * @throws {HttpError} When the request fails.
 */
export async function fetchUserById(id: number, signal?: AbortSignal): Promise<ManagedUser | null> {
  const dto = await apiFetch<UserDto | null>(`/users/${id}`, { signal })
  return dto ? mapManagedUser(dto) : null
}

/**
 * Sets a new password for a user (admin scope `users:write`). Authorised by the
 * administrator's own step-up, not by the target user's current password.
 *
 * @param userId - The target user id.
 * @param password - The new password.
 * @param stepUp - The administrator's step-up credentials.
 * @throws {HttpError} When the request fails (e.g. password too short, or a refused step-up).
 */
export async function changeUserPassword(
  userId: number,
  password: string,
  stepUp: StepUpInput,
): Promise<void> {
  await apiFetch<void>(`/users/${userId}/password/change`, {
    method: 'POST',
    body: JSON.stringify({
      password,
      step_up: toStepUpWire(stepUp),
    } satisfies Schemas['UserAdminEditPassword']),
    responseType: 'void',
  })
}

/**
 * Resets a user's two-factor authentication (admin scope `users:write`). The backend removes the user's MFA
 * secret and backup codes, ends all of their sessions and notifies them.
 *
 * @param userId - The target user id.
 * @param stepUp - The administrator's step-up credentials.
 * @throws {HttpError} When the request fails (`409` when the user has no MFA, `403` for a refused step-up).
 */
export async function resetUserMfa(userId: number, stepUp: StepUpInput): Promise<void> {
  await apiFetch<void>(`/users/${userId}/mfa/reset`, {
    method: 'POST',
    body: JSON.stringify({ step_up: toStepUpWire(stepUp) } satisfies StepUpRequestDto),
    responseType: 'void',
  })
}

/**
 * Requires a user to choose a new password at their next password sign-in (admin scope `users:write`). The
 * backend keeps the current password, ends all of the user's sessions and notifies them.
 *
 * @param userId - The target user id.
 * @param stepUp - The administrator's step-up credentials.
 * @throws {HttpError} When the request fails (`409` when the user has no local password, or a refused step-up).
 */
export async function requireUserPasswordChange(
  userId: number,
  stepUp: StepUpInput,
): Promise<void> {
  await apiFetch<void>(`/users/${userId}/password/require-change`, {
    method: 'POST',
    body: JSON.stringify({ step_up: toStepUpWire(stepUp) } satisfies StepUpRequestDto),
    responseType: 'void',
  })
}

/**
 * Uploads a new profile photo for a user (admin scope `users:write`). The image
 * is sent as multipart; the backend validates it and generates the stored
 * filename, returning the new photo path.
 *
 * @param userId - The target user id.
 * @param file - The image file selected by the admin.
 * @returns The new photo path, or `null` when none was stored.
 * @throws {HttpError} When the upload is rejected (e.g. an invalid image).
 */
export async function uploadUserPhoto(userId: number, file: File): Promise<string | null> {
  const formData = new FormData()
  // The third arg is the multipart part filename only; the backend sanitizes it
  // and generates its own storage filename, so it never reaches a path/URL.
  formData.append('file', file, file.name)
  const photo = await apiFetch<Schemas['UserPhotoRead']>(`/users/${userId}/photo`, {
    method: 'PUT',
    body: formData,
    timeoutMs: 0,
  })
  return photo.photo_path ?? null
}

/**
 * Removes a user's profile photo (admin scope `users:write`).
 *
 * @param userId - The target user id.
 * @throws {HttpError} When the request fails.
 */
export async function deleteUserPhoto(userId: number): Promise<void> {
  await apiFetch<void>(`/users/${userId}/photo`, { method: 'DELETE', responseType: 'void' })
}

/**
 * Queues the deletion of a user (admin scope `users:write`): the user is signed out and deactivated at once (202) and a background job erases their data.
 *
 * @param id - The user id to delete.
 * @param version - The user version the caller read, for `If-Match`.
 * @param stepUp - The administrator's step-up credentials.
 * @returns The deletion job; follow it with `useUserDeletionQuery`.
 * @throws {HttpError} When the request fails (`412` when the user changed since it was read).
 */
export async function deleteUser(
  id: number,
  version: number,
  stepUp: StepUpInput,
): Promise<UserDeletionStatus> {
  return apiFetch<UserDeletionStatus>(`/users/${id}/delete`, {
    method: 'POST',
    headers: ifMatchHeaders(version),
    body: JSON.stringify({ step_up: toStepUpWire(stepUp) } satisfies StepUpRequestDto),
  })
}

/**
 * Approves a pending sign-up (admin scope `users:write`). The backend clears the
 * pending flag and emails the user; rejection is a plain {@link deleteUser}.
 *
 * @param id - The user id to approve.
 * @throws {HttpError} When the request fails.
 */
export async function approveUser(id: number): Promise<void> {
  await apiFetch<void>(`/users/${id}/approve`, { method: 'POST', responseType: 'void' })
}
