import { computed, toValue, type MaybeRefOrGetter } from 'vue'
import { storeToRefs } from 'pinia'
import { useMutation, useQuery, useQueryClient } from '@tanstack/vue-query'
import { useRouter } from 'vue-router'

import type {
  ApiKeyCreateInput,
  BackupCodesResult,
  MfaEnableInput,
  MfaSetup,
  PasswordChangeInput,
  StepUpInput,
} from '@/features/security/types'

import { useInvalidatingMutation } from '@/composables/useInvalidatingMutation'
import { queryKeys } from '@/services/queryKeys'
import { useAuthStore } from '@/features/auth/stores/auth'
import {
  cancelEmailChange,
  changeEmail,
  changePassword,
  createApiKey,
  deleteAccount,
  deleteApiKey,
  disableMfa,
  enableMfa,
  fetchApiKeys,
  fetchBackupCodeStatus,
  fetchMfaStatus,
  fetchSessions,
  regenerateBackupCodes,
  resendEmailChange,
  revokeApiKey,
  revokeOtherSessions,
  revokeSession,
  setupMfa,
} from '@/features/security/services/security'

/**
 * Whether MFA is enabled for the authenticated user. Gated on authentication so
 * it never fires on the login screen.
 *
 * @returns The TanStack Query result for the MFA status.
 */
export function useMfaStatusQuery() {
  const { isAuthenticated } = storeToRefs(useAuthStore())

  return useQuery({
    queryKey: queryKeys.security.mfaStatus(),
    queryFn: ({ signal }) => fetchMfaStatus(signal),
    enabled: isAuthenticated,
  })
}

/**
 * The remaining-backup-codes summary. Only fetched while MFA is enabled, since
 * the backend has no codes to report otherwise.
 *
 * @param enabled - Whether MFA is enabled (gates the query).
 * @returns The TanStack Query result for the backup-code status.
 */
export function useBackupCodeStatusQuery(enabled: MaybeRefOrGetter<boolean>) {
  const { isAuthenticated } = storeToRefs(useAuthStore())

  return useQuery({
    queryKey: queryKeys.security.backupCodeStatus(),
    queryFn: ({ signal }) => fetchBackupCodeStatus(signal),
    enabled: computed(() => isAuthenticated.value && toValue(enabled)),
  })
}

/**
 * The authenticated user's active sessions. Gated on authentication.
 *
 * @returns The TanStack Query result for the sessions list.
 */
export function useSessionsQuery() {
  const { isAuthenticated } = storeToRefs(useAuthStore())

  return useQuery({
    queryKey: queryKeys.security.sessions(),
    queryFn: ({ signal }) => fetchSessions(signal),
    enabled: isAuthenticated,
  })
}

/**
 * Change-password mutation. Invalidates the sessions list on success since
 * `revokeOtherSessions` may have removed other devices.
 *
 * @returns The TanStack Query mutation for changing the password.
 */
export function useChangePasswordMutation() {
  const client = useQueryClient()

  return useMutation<void, Error, PasswordChangeInput>({
    mutationKey: queryKeys.security.all(),
    mutationFn: (input) => changePassword(input),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: queryKeys.security.sessions() })
    },
  })
}

/**
 * Begins MFA enrolment (returns the secret + QR image). No cache invalidation —
 * enrolment is only confirmed by {@link useEnableMfaMutation}.
 *
 * @returns The TanStack Query mutation for starting MFA setup.
 */
export function useSetupMfaMutation() {
  return useMutation<MfaSetup, Error, void>({
    mutationKey: queryKeys.security.all(),
    mutationFn: () => setupMfa(),
  })
}

/**
 * Completes MFA enrolment. Invalidates the MFA and backup-code status so both
 * cards reflect the newly enabled state.
 *
 * @returns The TanStack Query mutation for enabling MFA (resolves to backup codes).
 */
export function useEnableMfaMutation() {
  const client = useQueryClient()

  return useMutation<string[], Error, MfaEnableInput>({
    mutationKey: queryKeys.security.all(),
    mutationFn: (input) => enableMfa(input),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: queryKeys.security.all() })
    },
  })
}

/**
 * Disables MFA. Invalidates the MFA and backup-code status on success.
 *
 * @returns The TanStack Query mutation for disabling MFA.
 */
export function useDisableMfaMutation() {
  const client = useQueryClient()

  return useMutation<void, Error, StepUpInput>({
    mutationKey: queryKeys.security.all(),
    mutationFn: (input) => disableMfa(input),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: queryKeys.security.all() })
    },
  })
}

/**
 * Regenerates the MFA backup codes. Invalidates the backup-code status so the
 * remaining count refreshes; resolves to the new codes for one-time display.
 *
 * @returns The TanStack Query mutation for regenerating backup codes.
 */
export function useRegenerateBackupCodesMutation() {
  const client = useQueryClient()

  return useMutation<BackupCodesResult, Error, StepUpInput>({
    mutationKey: queryKeys.security.all(),
    mutationFn: (input) => regenerateBackupCodes(input),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: queryKeys.security.backupCodeStatus() })
    },
  })
}

/**
 * Revokes a single session. Invalidates the sessions list on success.
 *
 * @returns The TanStack Query mutation for revoking a session.
 */
export function useRevokeSessionMutation() {
  const client = useQueryClient()

  return useMutation<void, Error, string>({
    mutationKey: queryKeys.security.all(),
    mutationFn: (sessionId) => revokeSession(sessionId),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: queryKeys.security.sessions() })
    },
  })
}

/**
 * Revokes every other session in one action (a parallel fan-out over the
 * self-service delete endpoint). Invalidates the sessions list on settle so it
 * reflects the server-authoritative state even on a partial failure.
 *
 * @returns The TanStack Query mutation for revoking other sessions.
 */
export function useRevokeOtherSessionsMutation() {
  return useInvalidatingMutation<void, void>({
    mutationKey: queryKeys.security.all(),
    mutationFn: () => revokeOtherSessions(),
    invalidateKey: queryKeys.security.sessions(),
  })
}

/**
 * The authenticated user's API keys. Gated on authentication.
 *
 * @returns The TanStack Query result for the API-keys list.
 */
export function useApiKeysQuery() {
  const { isAuthenticated } = storeToRefs(useAuthStore())

  return useQuery({
    queryKey: queryKeys.security.apiKeys(),
    queryFn: ({ signal }) => fetchApiKeys(signal),
    enabled: isAuthenticated,
  })
}

/**
 * Creates an API key (step-up gated). Resolves to the one-time raw key for
 * immediate display, and invalidates the list so the new key appears.
 *
 * @returns The TanStack Query mutation for creating an API key.
 */
export function useCreateApiKeyMutation() {
  const client = useQueryClient()

  return useMutation<string, Error, ApiKeyCreateInput>({
    mutationKey: queryKeys.security.all(),
    mutationFn: (input) => createApiKey(input),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: queryKeys.security.apiKeys() })
    },
  })
}

/**
 * Revokes an API key (soft-disable). Invalidates the list so the row reflects
 * its revoked state.
 *
 * @returns The TanStack Query mutation for revoking an API key.
 */
export function useRevokeApiKeyMutation() {
  const client = useQueryClient()

  return useMutation<void, Error, string>({
    mutationKey: queryKeys.security.all(),
    mutationFn: (id) => revokeApiKey(id),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: queryKeys.security.apiKeys() })
    },
  })
}

/**
 * Permanently deletes an API key. Invalidates the list so the row disappears.
 *
 * @returns The TanStack Query mutation for deleting an API key.
 */
export function useDeleteApiKeyMutation() {
  const client = useQueryClient()

  return useMutation<void, Error, string>({
    mutationKey: queryKeys.security.all(),
    mutationFn: (id) => deleteApiKey(id),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: queryKeys.security.apiKeys() })
    },
  })
}

/**
 * Delete-my-account mutation. On success the account and its sessions no longer
 * exist on the server, so it leaves for the farewell page and then clears only
 * the local session; calling the logout endpoint would just fail. Navigation
 * comes first because clearing empties the Query cache, which unmounts the
 * calling view and with it any per-call `mutate` callback.
 *
 * @returns The TanStack Query mutation for deleting the account.
 */
export function useDeleteAccountMutation() {
  const authStore = useAuthStore()
  const router = useRouter()

  return useMutation<void, Error, StepUpInput>({
    mutationKey: queryKeys.security.all(),
    mutationFn: (input) => deleteAccount(input),
    onSuccess: async () => {
      await router.replace({ name: 'account-deleted' })
      authStore.clearLocalSession()
    },
  })
}

/**
 * Change-email mutation, run after step-up. The address and its verified state are shown by the
 * profile, the app shell and an admin's users views, so all of them are refetched.
 *
 * @returns The TanStack Query mutation for changing the account email.
 */
export function useChangeEmailMutation() {
  const invalidate = useInvalidateEmailViews()

  return useMutation<
    boolean,
    Error,
    { email: string; stepUp: StepUpInput; revokeOtherSessions: boolean }
  >({
    mutationKey: queryKeys.security.all(),
    mutationFn: ({ email, stepUp, revokeOtherSessions }) =>
      changeEmail(email, stepUp, revokeOtherSessions),
    onSettled: invalidate,
  })
}

/**
 * Invalidates every view of the account email, so the pending change shows (or disappears)
 * in the profile, the app shell and an admin's users views.
 */
function useInvalidateEmailViews(): () => void {
  const client = useQueryClient()
  return () => {
    void client.invalidateQueries({ queryKey: queryKeys.profile.all() })
    void client.invalidateQueries({ queryKey: queryKeys.currentUser() })
    void client.invalidateQueries({ queryKey: queryKeys.users.all() })
  }
}

/**
 * Resend mutation for the pending email-change confirmation link.
 *
 * @returns The TanStack Query mutation for resending the link.
 */
export function useResendEmailChangeMutation() {
  const invalidate = useInvalidateEmailViews()

  return useMutation<void, Error, void>({
    mutationKey: queryKeys.security.all(),
    mutationFn: () => resendEmailChange(),
    onSettled: invalidate,
  })
}

/**
 * Cancel mutation for the pending email change.
 *
 * @returns The TanStack Query mutation for cancelling the change.
 */
export function useCancelEmailChangeMutation() {
  const invalidate = useInvalidateEmailViews()

  return useMutation<void, Error, void>({
    mutationKey: queryKeys.security.all(),
    mutationFn: () => cancelEmailChange(),
    onSettled: invalidate,
  })
}
