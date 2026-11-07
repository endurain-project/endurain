import { storeToRefs } from 'pinia'
import { useMutation, useQuery, useQueryClient } from '@tanstack/vue-query'

import type {
  ActivityVisibility,
  PrivacySettings,
  ProfileDetails,
  ProfileEditInput,
} from '@/features/profile/types'
import type { User } from '@/features/auth/types'

import { useInvalidatingMutation } from '@/composables/useInvalidatingMutation'
import { queryKeys } from '@/services/queryKeys'
import { getLocaleForBackendLanguage, loadLocaleMessages, setI18nLocale } from '@/i18n'
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
  firstDayOfWeek: ProfileEditInput['firstDayOfWeek'] | undefined,
): void {
  if (firstDayOfWeek === undefined) {
    return
  }
  const currentUser = client.getQueryData<User>(queryKeys.currentUser())
  if (currentUser?.firstDayOfWeek === firstDayOfWeek) {
    return
  }
  void client.invalidateQueries({ queryKey: queryKeys.activities.all() })
  void client.invalidateQueries({ queryKey: queryKeys.goals.all() })
}

/**
 * Invalidates health data when the height changed, since BMI derives from it.
 *
 * @param client - The active query client.
 * @param height - Successfully persisted height in centimetres, or `null`.
 */
export function invalidateHeightDependentQueries(
  client: ReturnType<typeof useQueryClient>,
  height: ProfileEditInput['height'] | undefined,
): void {
  if (height === undefined) {
    return
  }
  const profile = client.getQueryData<ProfileDetails>(queryKeys.profile.detail())
  if (profile?.height === height) {
    return
  }
  void client.invalidateQueries({ queryKey: queryKeys.health.all() })
}

/**
 * Switches the interface to a newly saved preferred language, so a profile
 * edit takes effect without a reload.
 *
 * @param client - The active query client.
 * @param language - Successfully persisted language, if the edit sent one.
 */
async function applyChangedLanguage(
  client: ReturnType<typeof useQueryClient>,
  language: ProfileEditInput['preferredLanguage'] | undefined,
): Promise<void> {
  const profile = client.getQueryData<ProfileDetails>(queryKeys.profile.detail())
  const locale = getLocaleForBackendLanguage(language)
  if (!locale || profile?.preferredLanguage === language) {
    return
  }
  await loadLocaleMessages(locale)
  setI18nLocale(locale)
}

/**
 * Profile identity edit mutation. Sends only the fields given, applies a changed
 * language immediately, and invalidates the profile and shell caches.
 *
 * @returns The TanStack Query mutation for updating the profile.
 */
export function useUpdateProfileMutation() {
  const client = useQueryClient()

  return useMutation<void, Error, { input: Partial<ProfileEditInput>; version: number }>({
    mutationKey: queryKeys.profile.all(),
    mutationFn: ({ input, version }) => updateProfile(input, version),
    onSuccess: async (_data, { input }) => {
      invalidateWeekDependentQueries(client, input.firstDayOfWeek)
      invalidateHeightDependentQueries(client, input.height)
      await applyChangedLanguage(client, input.preferredLanguage)
    },
    onSettled: () => invalidateProfileAndShell(client),
  })
}

/**
 * Saves the preferred language to the profile, reading the profile fresh so the
 * write carries its current version. Skips the write when it already matches.
 *
 * @returns An async function taking the language to save.
 */
export function useSavePreferredLanguage() {
  const client = useQueryClient()
  const mutation = useUpdateProfileMutation()

  return async (language: ProfileEditInput['preferredLanguage']): Promise<void> => {
    const profile = await client.fetchQuery({
      queryKey: queryKeys.profile.detail(),
      queryFn: ({ signal }) => fetchProfile(signal),
      staleTime: 0,
    })
    if (profile.preferredLanguage === language) {
      return
    }
    await mutation.mutateAsync({ input: { preferredLanguage: language }, version: profile.version })
  }
}

/**
 * Privacy-settings update mutation. Only the profile cache is affected.
 *
 * @returns The TanStack Query mutation for updating privacy settings.
 */
export function useUpdatePrivacyMutation() {
  return useInvalidatingMutation<void, PrivacySettings>({
    mutationKey: queryKeys.profile.all(),
    mutationFn: (privacy) => updatePrivacySettings(privacy),
  })
}

/**
 * Existing-activities visibility mutation. Invalidates the activities domain so
 * lists, feeds, summaries, and detail views refetch the updated visibility.
 *
 * @returns The TanStack Query mutation for bulk-updating activity visibility.
 */
export function useUpdateExistingActivitiesVisibilityMutation() {
  return useInvalidatingMutation<void, ActivityVisibility>({
    mutationKey: queryKeys.activities.all(),
    mutationFn: (visibility) => updateUserActivitiesVisibility(visibility),
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
