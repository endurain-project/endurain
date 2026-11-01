import { beforeEach, describe, expect, it, vi } from 'vitest'

import type { PublicServerSettings } from '@/features/config/types'

import { queryClient } from '@/plugins/vueQuery'
import { HttpError } from '@/services/http'
import { queryKeys } from '@/services/queryKeys'
import {
  DEFAULT_PUBLIC_SERVER_SETTINGS,
  fetchPublicServerSettings,
} from '@/features/config/services/serverSettings'
import { loadAppConfig, useAppConfig } from '@/features/config/composables/useAppConfig'

vi.mock('@/features/config/services/serverSettings', async (importActual) => {
  const actual = await importActual<typeof import('@/features/config/services/serverSettings')>()
  return { ...actual, fetchPublicServerSettings: vi.fn<typeof actual.fetchPublicServerSettings>() }
})

vi.mock('@/composables/useTelemetry', () => ({
  useTelemetry: () => ({ captureError: vi.fn<() => void>() }),
}))

describe('loadAppConfig configuration-error detection', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    queryClient.clear()
  })

  it('raises configError when the backend host is unreachable (non-HTTP failure)', async () => {
    vi.mocked(fetchPublicServerSettings).mockRejectedValueOnce(new TypeError('Failed to fetch'))

    await loadAppConfig()

    expect(useAppConfig().configError.value).toBe(true)
  })

  it('raises configError when the request times out', async () => {
    vi.mocked(fetchPublicServerSettings).mockRejectedValueOnce(
      new DOMException('The operation timed out.', 'TimeoutError'),
    )

    await loadAppConfig()

    expect(useAppConfig().configError.value).toBe(true)
  })

  it('stays quiet when the backend is reachable but answers with an HTTP error', async () => {
    vi.mocked(fetchPublicServerSettings).mockRejectedValueOnce(
      new HttpError(500, 'Internal Server Error'),
    )

    await loadAppConfig()

    expect(useAppConfig().configError.value).toBe(false)
  })

  it('clears a previous config error once the backend becomes reachable', async () => {
    vi.mocked(fetchPublicServerSettings).mockRejectedValueOnce(new TypeError('Failed to fetch'))
    await loadAppConfig()
    expect(useAppConfig().configError.value).toBe(true)

    vi.mocked(fetchPublicServerSettings).mockResolvedValueOnce(DEFAULT_PUBLIC_SERVER_SETTINGS)
    await loadAppConfig()
    expect(useAppConfig().configError.value).toBe(false)
  })
})

describe('loadAppConfig settings cache', () => {
  const settings: PublicServerSettings = {
    ...DEFAULT_PUBLIC_SERVER_SETTINGS,
    signup_enabled: !DEFAULT_PUBLIC_SERVER_SETTINGS.signup_enabled,
    num_records_per_page: 50,
  }

  beforeEach(() => {
    vi.clearAllMocks()
    queryClient.clear()
  })

  it('derives the app config from the public server settings', async () => {
    vi.mocked(fetchPublicServerSettings).mockResolvedValueOnce(settings)

    await loadAppConfig()

    expect(fetchPublicServerSettings).toHaveBeenCalledOnce()
    expect(useAppConfig().config.value.features.signUp).toBe(settings.signup_enabled)
  })

  it('seeds the public settings query, so the first screen reads them without another request', async () => {
    vi.mocked(fetchPublicServerSettings).mockResolvedValueOnce(settings)

    await loadAppConfig()

    expect(queryClient.getQueryData(queryKeys.public.serverSettings())).toEqual(settings)
    expect(queryClient.getQueryState(queryKeys.public.serverSettings())?.isInvalidated).toBe(false)
  })

  it('caches nothing when the settings cannot be loaded, and leaves the config as it was', async () => {
    const before = useAppConfig().config.value
    vi.mocked(fetchPublicServerSettings).mockRejectedValueOnce(new TypeError('Failed to fetch'))

    await loadAppConfig()

    expect(queryClient.getQueryData(queryKeys.public.serverSettings())).toBeUndefined()
    expect(useAppConfig().config.value).toBe(before)
  })
})
