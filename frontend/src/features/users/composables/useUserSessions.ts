import { computed, type MaybeRefOrGetter, toValue } from 'vue'
import { storeToRefs } from 'pinia'
import { useMutation, useQuery, useQueryClient } from '@tanstack/vue-query'

import type { StepUpInput } from '@/features/security/types'
import type { UserSession } from '@/features/users/types'

import { queryKeys } from '@/services/queryKeys'
import { useAuthStore } from '@/features/auth/stores/auth'
import {
  fetchUserSessions,
  revokeOtherUserSessions,
  revokeUserSession,
} from '@/features/users/services/sessions'

/**
 * A user's active sessions for the admin detail page. Gated on authentication
 * and a positive id (a bad route id keeps the query disabled).
 *
 * @param userId - Reactive target user id (or `null` before it resolves).
 * @returns The TanStack Query result for the user's sessions.
 */
export function useUserSessionsQuery(userId: MaybeRefOrGetter<number | null>) {
  const { isAuthenticated } = storeToRefs(useAuthStore())

  return useQuery<UserSession[]>({
    queryKey: computed(() => queryKeys.users.sessions(toValue(userId) ?? 0)),
    queryFn: ({ signal }) => fetchUserSessions(toValue(userId) as number, signal),
    enabled: computed(() => isAuthenticated.value && (toValue(userId) ?? 0) > 0),
  })
}

/**
 * Session-revocation mutation. Invalidates the owner's sessions list on success
 * so the revoked device drops out of the view.
 *
 * @returns The TanStack Query mutation for revoking a user's session.
 */
export function useRevokeUserSessionMutation() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: ({
      sessionId,
      userId,
      stepUp,
    }: {
      sessionId: string
      userId: number
      stepUp: StepUpInput
    }) => revokeUserSession(sessionId, userId, stepUp),
    onSuccess: (_data, { userId }) => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.users.sessions(userId) })
    },
  })
}

/**
 * Bulk session-revocation mutation: revokes every session for a user, keeping
 * `excludeSessionId` (the caller's current session) when provided. Invalidates
 * the owner's sessions list on success.
 *
 * @returns The TanStack Query mutation for revoking a user's other sessions.
 */
export function useRevokeOtherUserSessionsMutation() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: ({
      userId,
      stepUp,
      excludeSessionId,
    }: {
      userId: number
      stepUp: StepUpInput
      excludeSessionId?: string
    }) => revokeOtherUserSessions(userId, stepUp, excludeSessionId),
    onSuccess: (_data, { userId }) => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.users.sessions(userId) })
    },
  })
}
