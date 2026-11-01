import { computed, type MaybeRefOrGetter, toValue } from 'vue'
import { storeToRefs } from 'pinia'
import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/vue-query'

import type {
  CreateUserInput,
  EditUserFields,
  ManagedUser,
  UserFilters,
} from '@/features/users/types'

import { queryKeys } from '@/services/queryKeys'
import { bumpAvatarCacheToken } from '@/lib/avatarCache'
import { useInvalidatingMutation } from '@/composables/useInvalidatingMutation'
import { useAuthStore } from '@/features/auth/stores/auth'
import {
  approveUser,
  changeUserPassword,
  createUser,
  deleteUser,
  deleteUserPhoto,
  fetchUserById,
  fetchUsers,
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
  return useInvalidatingMutation<ManagedUser, CreateUserInput>({
    mutationKey: queryKeys.users.all(),
    mutationFn: (input) => createUser(input),
  })
}

/**
 * Update mutation. Invalidates the users domain on settle.
 *
 * @returns The TanStack Query mutation for updating a user.
 */
export function useUpdateUserMutation() {
  return useInvalidatingMutation<ManagedUser, { user: ManagedUser; edits: EditUserFields }>({
    mutationKey: queryKeys.users.all(),
    mutationFn: ({ user, edits }) => updateUser(user, edits),
  })
}

/**
 * Delete mutation. Invalidates the users domain on settle.
 *
 * @returns The TanStack Query mutation for deleting a user.
 */
export function useDeleteUserMutation() {
  return useInvalidatingMutation<void, { id: number; version: number }>({
    mutationKey: queryKeys.users.all(),
    mutationFn: ({ id, version }) => deleteUser(id, version),
  })
}

/**
 * Approve mutation for a pending sign-up. Invalidates the users domain on settle
 * so the detail badge and the list both refresh.
 *
 * @returns The TanStack Query mutation for approving a user.
 */
export function useApproveUserMutation() {
  return useInvalidatingMutation<void, number>({
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
export function useUserQuery(id: MaybeRefOrGetter<number | null>) {
  const { isAuthenticated } = storeToRefs(useAuthStore())

  return useQuery({
    queryKey: computed(() => queryKeys.users.detail(toValue(id) ?? 0)),
    queryFn: ({ signal }) => fetchUserById(toValue(id) as number, signal),
    enabled: computed(() => isAuthenticated.value && (toValue(id) ?? 0) > 0),
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
    mutationFn: ({ userId, password }: { userId: number; password: string }) =>
      changeUserPassword(userId, password),
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
    mutationFn: ({ userId, file }: { userId: number; file: File }) => uploadUserPhoto(userId, file),
    onSuccess: (_data, { userId }) => {
      // Bust the avatar cache so the replaced photo re-fetches (stable path).
      bumpAvatarCacheToken()
      void queryClient.invalidateQueries({ queryKey: queryKeys.users.detail(userId) })
      void queryClient.invalidateQueries({ queryKey: queryKeys.users.lists() })
      void queryClient.invalidateQueries({ queryKey: queryKeys.currentUser() })
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
    mutationFn: (userId: number) => deleteUserPhoto(userId),
    onSuccess: (_data, userId) => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.users.detail(userId) })
      void queryClient.invalidateQueries({ queryKey: queryKeys.users.lists() })
      void queryClient.invalidateQueries({ queryKey: queryKeys.currentUser() })
    },
  })
}
