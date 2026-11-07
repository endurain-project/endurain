import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import i18n from '@/i18n'
import StravaCallbackView from '@/features/integrations/views/StravaCallbackView.vue'
import { HttpError } from '@/services/http'

const { completeStravaLink, toastError, toastSuccess, routerReplace, route } = vi.hoisted(() => ({
  route: { query: {} as Record<string, unknown> },
  routerReplace: vi.fn<(to: unknown) => Promise<void>>(() => Promise.resolve()),
  completeStravaLink: vi.fn<(state: string, code: string, scope: string) => Promise<void>>(),
  toastError: vi.fn<(message: string) => void>(),
  toastSuccess: vi.fn<(message: string) => void>(),
}))

vi.mock('vue-router', () => ({
  useRoute: () => route,
  useRouter: () => ({ replace: routerReplace }),
}))
vi.mock('@tanstack/vue-query', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@tanstack/vue-query')>()),
  useQueryClient: () => ({ invalidateQueries: vi.fn<() => Promise<void>>() }),
}))
vi.mock('@/composables/useToasts', () => ({
  useToasts: () => ({ success: toastSuccess, error: toastError }),
}))
vi.mock('@/features/integrations/services/strava', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/features/integrations/services/strava')>()),
  completeStravaLink,
}))

/**
 * Mounts the callback view and waits for the on-mount link to settle.
 */
async function mountView() {
  mount(StravaCallbackView, { global: { plugins: [i18n] } })
  await flushPromises()
}

describe('StravaCallbackView', () => {
  beforeEach(() => {
    route.query = { state: 's', code: 'c', scope: 'read,profile:read_all,activity:read_all' }
    completeStravaLink.mockReset()
    toastError.mockReset()
    toastSuccess.mockReset()
    routerReplace.mockClear()
  })

  it('sends the granted scope with the state and code', async () => {
    completeStravaLink.mockResolvedValue(undefined)

    await mountView()

    expect(completeStravaLink).toHaveBeenCalledWith(
      's',
      'c',
      'read,profile:read_all,activity:read_all',
    )
    expect(toastSuccess).toHaveBeenCalledOnce()
  })

  it('explains a grant that lacks a required permission', async () => {
    completeStravaLink.mockRejectedValue(
      new HttpError(400, 'Bad Request', null, 'urn:endurain:error:provider-scope-insufficient'),
    )

    await mountView()

    expect(toastError).toHaveBeenCalledWith(
      i18n.global.t('settings.integrations.strava.scopeError'),
    )
  })

  it('shows the generic error for any other failure', async () => {
    completeStravaLink.mockRejectedValue(new HttpError(400, 'Bad Request'))

    await mountView()

    expect(toastError).toHaveBeenCalledWith(
      i18n.global.t('settings.integrations.strava.connectError'),
    )
  })

  it('refuses a callback without a scope before calling the server', async () => {
    route.query = { state: 's', code: 'c' }

    await mountView()

    expect(completeStravaLink).not.toHaveBeenCalled()
    expect(toastError).toHaveBeenCalledOnce()
  })
})
