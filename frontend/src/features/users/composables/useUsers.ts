import { computed, type MaybeRefOrGetter, toValue, watch } from 'vue'
import { storeToRefs } from 'pinia'
import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/vue-query'

import type { User } from '@/features/auth/types'
import type { StepUpInput } from '@/features/security/types'
import type {
  CreateUserInput,
  EditUserFields,
  ManagedUser,
  UserFilters,
} from '@/features/users/types'

import { queryKeys } from '@/services/queryKeys'
import { useUserDeletionsStore } from '@/features/users/stores/userDeletions'
import { seedJob } from '@/services/jobStatus'
import { useJobQuery } from '@/composables/useJobQuery'
import { bumpAvatarCacheToken } from '@/lib/avatarCache'
import { useInvalidatingMutation } from '@/composables/useInvalidatingMutation'
import { useAuthStore } from '@/features/auth/stores/auth'
import { invalidateHeightDependentQueries } from '@/features/profile/composables/useProfile'
import {
  approveUser,
  changeUserPassword,
  createUser,
  deleteUser,
  deleteUserPhoto,
  fetchUserById,
  fetchUsers,
  requireUserPasswordChange,
  resetUserMfa,
  updateUser,
  uploadUserPhoto,
} from '@/features/users/services/users'

/**
 * One page of all users, driven by numbered pagination so the page size honours
 * the server's `num_records_per_page` setting. Keyed on page + size + the active
 * filter set; uses `keepPreviousData` so paging keeps the current rows visible
 * until the next page resolves. Gated on authentication.
 *
 * @param page - Reactive 1-based page number.
 * @param pageSize - Reactive records-per-page (from server settings).
 * @param filters - Reactive list filters (inactive, unverified, etc.) and the optional
 *   username search term.
 * @returns The TanStack Query result for the current users page.
 */
export function useUsersQuery(
  page: MaybeRefOrGetter<number>,
  pageSize: MaybeRefOrGetter<number>,
  filters: MaybeRefOrGetter<UserFilters & { username?: string }>,
) {
  const { isAuthenticated } = storeToRefs(useAuthStore())

  return useQuery({
    queryKey: computed(() =>
      queryKeys.users.list({
        page: toValue(page),
        numRecords: toValue(pageSize),
        ...toValue(filters),
      }),
    ),
    queryFn: ({ signal }) =>
      fetchUsers(
        {
          page: toValue(page),
          numRecords: toValue(pageSize),
          ...toValue(filters),
        },
        signal,
      ),
    placeholderData: keepPreviousData,
    enabled: isAuthenticated,
  })
}

/**
 * Create mutation. Invalidates the users domain on settle so every list and the
 * username search refetch the server-authoritative state.
 *
 * @returns The TanStack Query mutation for creating a user.
 */
export function useCreateUserMutation() {
  return useInvalidatingMutation<
    ManagedUser,
    { input: CreateUserInput; stepUp: StepUpInput | null }
  >({
    mutationKey: queryKeys.users.all(),
    mutationFn: ({ input, stepUp }) => createUser(input, stepUp),
  })
}

/**
 * Update mutation. Invalidates the users domain on settle, and the health data
 * when the signed-in user's own height changed, since BMI derives from it.
 *
 * @returns The TanStack Query mutation for updating a user.
 */
export function useUpdateUserMutation() {
  const client = useQueryClient()

  return useInvalidatingMutation<
    ManagedUser,
    {
      user: ManagedUser
      edits: EditUserFields
      stepUp?: StepUpInput | null
    }
  >({
    mutationKey: queryKeys.users.all(),
    alsoInvalidate: [queryKeys.profile.all()],
    mutationFn: async ({ user, edits, stepUp }) => {
      const updated = await updateUser(user, edits, stepUp)
      if (client.getQueryData<User>(queryKeys.currentUser())?.id === user.id) {
        invalidateHeightDependentQueries(client, edits.height)
      }
      return updated
    },
  })
}

/**
 * Delete mutation. Invalidates the users domain on settle, and follows the queued deletion.
 *
 * @returns The TanStack Query mutation for deleting a user.
 */
export function useDeleteUserMutation() {
  const client = useQueryClient()
  const deletions = useUserDeletionsStore()

  return useInvalidatingMutation<void, { id: string; version: number; stepUp: StepUpInput }>({
    mutationKey: queryKeys.users.all(),
    mutationFn: async ({ id, version, stepUp }) => {
      const job = await deleteUser(id, version, stepUp)
      seedJob(client, job)
      deletions.track(id, job.id)
    },
  })
}

/** How often a queued account deletion is read again; the backend asks for 10 seconds. */
const DELETION_POLL_MS = 10_000

/**
 * Follows a queued account deletion until it reaches a terminal state. Once it has succeeded,
 * the users lists and details are refetched, so the erased account leaves the screen.
 *
 * @param jobId - The deletion job's id, from the 202 that queued it.
 * @returns The query; `data` is the deletion job's state.
 */
export function useUserDeletionQuery(jobId: MaybeRefOrGetter<string>) {
  const client = useQueryClient()
  const query = useJobQuery<'user_deletion'>(jobId, { intervalMs: DELETION_POLL_MS })

  watch(
    () => query.data.value?.status,
    (status) => {
      if (status === 'succeeded') {
        void client.invalidateQueries({ queryKey: queryKeys.users.lists() })
        void client.invalidateQueries({ queryKey: queryKeys.users.details() })
      }
    },
  )

  return query
}

/**
 * Approve mutation for a pending sign-up. Invalidates the users domain on settle
 * so the detail badge and the list both refresh.
 *
 * @returns The TanStack Query mutation for approving a user.
 */
export function useApproveUserMutation() {
  return useInvalidatingMutation<void, string>({
    mutationKey: queryKeys.users.all(),
    mutationFn: (id) => approveUser(id),
  })
}

/**
 * A single user by id for the admin detail page. Gated on authentication and a
 * positive id; the detail cache is independent of the list cache.
 *
 * @param id - Reactive user id (or `null` before it resolves / for a bad route).
 * @returns The TanStack Query result for the user.
 */
export function useUserQuery(id: MaybeRefOrGetter<string | null>) {
  const { isAuthenticated } = storeToRefs(useAuthStore())

  return useQuery({
    queryKey: computed(() => queryKeys.users.detail(toValue(id) ?? '')),
    queryFn: ({ signal }) => fetchUserById(toValue(id) as string, signal),
    enabled: computed(() => isAuthenticated.value && toValue(id) !== null),
    // While the account waits to be erased, read it again until it is gone.
    refetchInterval: (state) => (state.state.data?.deletionRequestedAt ? DELETION_POLL_MS : false),
  })
}

/**
 * Admin password-reset mutation. Sets a new password for the target user; it
 * doesn't change any cached list/detail data, so nothing is invalidated.
 *
 * @returns The TanStack Query mutation for resetting a user's password.
 */
export function useChangeUserPasswordMutation() {
  return useMutation({
    mutationFn: ({
      userId,
      password,
      stepUp,
    }: {
      userId: string
      password: string
      stepUp: StepUpInput
    }) => changeUserPassword(userId, password, stepUp),
  })
}

/**
 * Admin MFA-reset mutation. Invalidates the users domain on settle: the user's MFA flag changes and their
 * sessions end.
 *
 * @returns The TanStack Query mutation for resetting a user's MFA.
 */
export function useResetUserMfaMutation() {
  return useInvalidatingMutation<void, { userId: string; stepUp: StepUpInput }>({
    mutationKey: queryKeys.users.all(),
    mutationFn: ({ userId, stepUp }) => resetUserMfa(userId, stepUp),
  })
}

/**
 * Admin mutation that requires a user to change their password at the next sign-in. Invalidates the users
 * domain on settle: the user's sessions end.
 *
 * @returns The TanStack Query mutation for requiring a password change.
 */
export function useRequireUserPasswordChangeMutation() {
  return useInvalidatingMutation<void, { userId: string; stepUp: StepUpInput }>({
    mutationKey: queryKeys.users.all(),
    mutationFn: ({ userId, stepUp }) => requireUserPasswordChange(userId, stepUp),
  })
}

/**
 * User photo upload mutation. Refreshes the user's detail and the list (and the
 * current-user profile, in case an admin edited their own photo).
 *
 * @returns The TanStack Query mutation for uploading a user's photo.
 */
export function useUploadUserPhotoMutation() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: ({ userId, file }: { userId: string; file: File }) => uploadUserPhoto(userId, file),
    onSuccess: (_data, { userId }) => {
      // Bust the avatar cache so the replaced photo re-fetches (stable path).
      bumpAvatarCacheToken()
      void queryClient.invalidateQueries({ queryKey: queryKeys.users.detail(userId) })
      void queryClient.invalidateQueries({ queryKey: queryKeys.users.lists() })
      void queryClient.invalidateQueries({ queryKey: queryKeys.currentUser() })
      void queryClient.invalidateQueries({ queryKey: queryKeys.profile.all() })
    },
  })
}

/**
 * User photo deletion mutation. Refreshes the same caches as the upload.
 *
 * @returns The TanStack Query mutation for removing a user's photo.
 */
export function useDeleteUserPhotoMutation() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: (userId: string) => deleteUserPhoto(userId),
    onSuccess: (_data, userId) => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.users.detail(userId) })
      void queryClient.invalidateQueries({ queryKey: queryKeys.users.lists() })
      void queryClient.invalidateQueries({ queryKey: queryKeys.currentUser() })
      void queryClient.invalidateQueries({ queryKey: queryKeys.profile.all() })
    },
  })
}
