import { storeToRefs } from 'pinia'
import { useMutation, useQuery, useQueryClient } from '@tanstack/vue-query'

import type {
  ActivityVisibility,
  PrivacySettings,
  ProfileEditInput,
} from '@/features/profile/types'
import type { User } from '@/features/auth/types'

import { queryKeys } from '@/services/queryKeys'
import { bumpAvatarCacheToken } from '@/lib/avatarCache'
import { useAuthStore } from '@/features/auth/stores/auth'
import { updateUserActivitiesVisibility } from '@/features/activities/services/activities'
import {
  deleteProfilePhoto,
  fetchProfile,
  updatePrivacySettings,
  updateProfile,
  uploadProfilePhoto,
} from '@/features/profile/services/profile'

/**
 * The authenticated user's full settings profile. Gated on authentication.
 *
 * @returns The TanStack Query result for the profile.
 */
export function useProfileQuery() {
  const { isAuthenticated } = storeToRefs(useAuthStore())

  return useQuery({
    queryKey: queryKeys.profile.detail(),
    queryFn: ({ signal }) => fetchProfile(signal),
    enabled: isAuthenticated,
  })
}

/**
 * Invalidates the profile detail and the shell's current-user caches. Identity
 * and photo edits change the navbar name/avatar (read from `currentUser`), so a
 * write must refresh both.
 *
 * @param client - The active query client.
 */
function invalidateProfileAndShell(client: ReturnType<typeof useQueryClient>): void {
  void client.invalidateQueries({ queryKey: queryKeys.profile.all() })
  void client.invalidateQueries({ queryKey: queryKeys.currentUser() })
}

/**
 * Invalidates data whose date range depends on the first weekday.
 *
 * @param client - The active query client.
 * @param firstDayOfWeek - Successfully persisted first weekday.
 */
function invalidateWeekDependentQueries(
  client: ReturnType<typeof useQueryClient>,
  firstDayOfWeek: ProfileEditInput['firstDayOfWeek'],
): void {
  const currentUser = client.getQueryData<User>(queryKeys.currentUser())
  if (currentUser?.firstDayOfWeek === firstDayOfWeek) {
    return
  }
  void client.invalidateQueries({ queryKey: queryKeys.activities.all() })
  void client.invalidateQueries({ queryKey: queryKeys.goals.all() })
}

/**
 * Profile identity edit mutation. Invalidates the profile and shell caches.
 *
 * @returns The TanStack Query mutation for updating the profile.
 */
export function useUpdateProfileMutation() {
  const client = useQueryClient()

  return useMutation<void, Error, ProfileEditInput>({
    mutationKey: queryKeys.profile.all(),
    mutationFn: (input) => updateProfile(input),
    onSuccess: (_data, input) => invalidateWeekDependentQueries(client, input.firstDayOfWeek),
    onSettled: () => invalidateProfileAndShell(client),
  })
}

/**
 * Privacy-settings update mutation. Only the profile cache is affected.
 *
 * @returns The TanStack Query mutation for updating privacy settings.
 */
export function useUpdatePrivacyMutation() {
  const client = useQueryClient()

  return useMutation<void, Error, PrivacySettings>({
    mutationKey: queryKeys.profile.all(),
    mutationFn: (privacy) => updatePrivacySettings(privacy),
    onSettled: () => {
      void client.invalidateQueries({ queryKey: queryKeys.profile.all() })
    },
  })
}

/**
 * Existing-activities visibility mutation. Invalidates the activities domain so
 * lists, feeds, summaries, and detail views refetch the updated visibility.
 *
 * @returns The TanStack Query mutation for bulk-updating activity visibility.
 */
export function useUpdateExistingActivitiesVisibilityMutation() {
  const client = useQueryClient()

  return useMutation<void, Error, ActivityVisibility>({
    mutationKey: queryKeys.activities.all(),
    mutationFn: (visibility) => updateUserActivitiesVisibility(visibility),
    onSettled: () => {
      void client.invalidateQueries({ queryKey: queryKeys.activities.all() })
    },
  })
}

/**
 * Profile-photo upload mutation. Invalidates the profile and shell caches so
 * the avatar refreshes everywhere.
 *
 * @returns The TanStack Query mutation for uploading the profile photo.
 */
export function useUploadProfilePhotoMutation() {
  const client = useQueryClient()

  return useMutation<void, Error, File>({
    mutationKey: queryKeys.profile.all(),
    mutationFn: (file) => uploadProfilePhoto(file),
    // Bust the avatar cache before the refetch so the new photo (served from
    // the same stable path) actually re-fetches instead of using the cache.
    onSuccess: () => bumpAvatarCacheToken(),
    onSettled: () => invalidateProfileAndShell(client),
  })
}

/**
 * Profile-photo deletion mutation. Invalidates the same caches as the upload.
 *
 * @returns The TanStack Query mutation for removing the profile photo.
 */
export function useDeleteProfilePhotoMutation() {
  const client = useQueryClient()

  return useMutation<void, Error, void>({
    mutationKey: queryKeys.profile.all(),
    mutationFn: () => deleteProfilePhoto(),
    onSettled: () => invalidateProfileAndShell(client),
  })
}
