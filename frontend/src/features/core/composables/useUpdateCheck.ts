import { computed } from 'vue'
import { useQuery } from '@tanstack/vue-query'

import { queryKeys } from '@/services/queryKeys'
import { useIsAdmin } from '@/features/auth/composables/useCurrentUser'
import {
  fetchBackendVersion,
  fetchLatestPreRelease,
  fetchLatestRelease,
  isNewerVersion,
  isPreRelease,
} from '@/features/core/services/updateCheck'

/** How often to re-check for a new release (every 6 hours). */
const RELEASE_STALE_MS = 6 * 60 * 60 * 1_000

/**
 * Checks whether a newer Endurain release is available.
 *
 * Both queries are gated on the user being an admin so that the external HTTP
 * request to GitHub is never made for regular users. Results are cached for
 * 6 hours to avoid hammering the external API on every page load.
 *
 * @returns
 *   - `updateAvailable` — `true` when the latest published release is strictly
 *     newer than the running backend version.
 *   - `latestVersion` — the latest version string when an update is available,
 *     `null` otherwise.
 */
export function useUpdateCheck() {
  const isAdmin = useIsAdmin()

  const { data: currentVersion } = useQuery({
    queryKey: queryKeys.core.aboutVersion(),
    queryFn: ({ signal }) => fetchBackendVersion(signal),
    enabled: isAdmin,
    staleTime: RELEASE_STALE_MS,
    gcTime: RELEASE_STALE_MS,
  })

  const { data: latestVersion } = useQuery({
    queryKey: queryKeys.core.latestRelease(),
    queryFn: ({ signal }) => fetchLatestRelease(signal),
    enabled: isAdmin,
    staleTime: RELEASE_STALE_MS,
    gcTime: RELEASE_STALE_MS,
  })

  const onPreRelease = computed(() => !!currentVersion.value && isPreRelease(currentVersion.value))

  const { data: latestPreRelease } = useQuery({
    queryKey: queryKeys.core.latestPreRelease(),
    queryFn: ({ signal }) => fetchLatestPreRelease(signal),
    enabled: computed(() => isAdmin.value && onPreRelease.value),
    staleTime: RELEASE_STALE_MS,
    gcTime: RELEASE_STALE_MS,
  })

  const updateAvailable = computed(() => {
    const current = currentVersion.value
    if (!current) return false
    const candidates = [latestVersion.value, latestPreRelease.value].filter((v): v is string => !!v)
    return candidates.some((v) => isNewerVersion(current, v))
  })

  const bestLatest = computed(() => {
    const current = currentVersion.value
    if (!current) return null
    const newer = [latestVersion.value, latestPreRelease.value].filter(
      (v): v is string => !!v && isNewerVersion(current, v),
    )
    return newer.reduce<string | null>(
      (best, v) => (!best || isNewerVersion(best, v) ? v : best),
      null,
    )
  })

  return {
    updateAvailable,
    latestVersion: computed(() => (updateAvailable.value ? bestLatest.value : null)),
  }
}
