import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import {
  consumeIdpStepUpReturn,
  isIdpReauthRequired,
  useIdpStepUp,
} from '@/features/security/composables/useIdpStepUp'
import { HttpError } from '@/services/http'

const mocks = vi.hoisted(() => ({
  startIdpStepUp: vi.fn<(...args: unknown[]) => Promise<string>>(),
}))

vi.mock('vue-router', () => ({ useRoute: () => ({ path: '/settings/security' }) }))
vi.mock('vue-i18n', () => ({ useI18n: () => ({ t: (key: string) => key }) }))
vi.mock('@tanstack/vue-query', () => ({ useQueryClient: () => ({}) }))
vi.mock('@/features/security/services/idpStepUp', () => ({
  startIdpStepUp: mocks.startIdpStepUp,
}))

const KEY = 'idp_step_up'

function store(overrides: Record<string, unknown> = {}): void {
  sessionStorage.setItem(
    KEY,
    JSON.stringify({
      action: 'api_key_create',
      verifier: 'verifier-1',
      idpId: 3,
      pending: { name: 'ci' },
      createdAt: Date.now(),
      ...overrides,
    }),
  )
}

function setUrl(suffix: string): void {
  history.replaceState({ keep: true }, '', `/settings/security${suffix}`)
}

describe('consumeIdpStepUpReturn', () => {
  beforeEach(() => {
    sessionStorage.clear()
    setUrl('')
  })
  afterEach(() => sessionStorage.clear())

  it('returns null and leaves the URL alone without a step-up result', () => {
    setUrl('?tab=1#other=1')
    store()
    expect(consumeIdpStepUpReturn()).toBeNull()
    expect(window.location.hash).toBe('#other=1')
    expect(sessionStorage.getItem(KEY)).not.toBeNull()
  })

  it('pairs a ticket with the stored entry, strips the fragment and removes the entry', () => {
    store()
    setUrl('?tab=1#step_up_ticket=abc')
    expect(consumeIdpStepUpReturn()).toEqual({
      action: 'api_key_create',
      reauth: { ticket: 'abc', codeVerifier: 'verifier-1' },
      pending: { name: 'ci' },
    })
    expect(window.location.hash).toBe('')
    expect(window.location.pathname + window.location.search).toBe('/settings/security?tab=1')
    expect(history.state).toEqual({ keep: true })
    expect(sessionStorage.getItem(KEY)).toBeNull()
  })

  it.each([
    ['failed', 'failed'],
    ['not_fresh', 'not_fresh'],
    ['anything', 'failed'],
  ])('reports step_up_error=%s as %s and drops the entry', (fragment, expected) => {
    store()
    setUrl(`#step_up_error=${fragment}`)
    expect(consumeIdpStepUpReturn()).toEqual({ error: expected })
    expect(window.location.hash).toBe('')
    expect(sessionStorage.getItem(KEY)).toBeNull()
  })

  it('fails when the stored entry is older than ten minutes', () => {
    store({ createdAt: Date.now() - 10 * 60 * 1000 - 1 })
    setUrl('#step_up_ticket=abc')
    expect(consumeIdpStepUpReturn()).toEqual({ error: 'failed' })
    expect(sessionStorage.getItem(KEY)).toBeNull()
  })

  it('fails when a ticket returns without a stored entry', () => {
    setUrl('#step_up_ticket=abc')
    expect(consumeIdpStepUpReturn()).toEqual({ error: 'failed' })
  })

  it('fails when the stored entry is malformed', () => {
    sessionStorage.setItem(KEY, '{not json')
    setUrl('#step_up_ticket=abc')
    expect(consumeIdpStepUpReturn()).toEqual({ error: 'failed' })
  })
})

describe('useIdpStepUp.start', () => {
  beforeEach(() => {
    sessionStorage.clear()
    mocks.startIdpStepUp.mockReset()
  })

  it('sends the S256 challenge, action and route path, stores the verifier and navigates', async () => {
    const assign = vi.fn<(url: string) => void>()
    vi.stubGlobal('location', { ...window.location, assign })
    mocks.startIdpStepUp.mockResolvedValue('https://idp.test/authorize')

    await useIdpStepUp().start(7, 'idp_unlink', { type: 'unlink', idpId: 7 })

    const [idpId, action, challenge, redirect] = mocks.startIdpStepUp.mock.calls[0] as [
      number,
      string,
      string,
      string,
    ]
    expect([idpId, action, redirect]).toEqual([7, 'idp_unlink', '/settings/security'])
    expect(challenge).toMatch(/^[A-Za-z0-9_-]{43}$/)
    const stored = JSON.parse(sessionStorage.getItem(KEY) ?? '{}') as Record<string, unknown>
    expect(stored).toMatchObject({
      action: 'idp_unlink',
      idpId: 7,
      pending: { type: 'unlink', idpId: 7 },
    })
    expect(typeof stored.verifier).toBe('string')
    expect(assign).toHaveBeenCalledWith('https://idp.test/authorize')
    vi.unstubAllGlobals()
  })

  it('stores nothing and does not navigate when the start request fails', async () => {
    const assign = vi.fn<(url: string) => void>()
    vi.stubGlobal('location', { ...window.location, assign })
    mocks.startIdpStepUp.mockRejectedValue(new HttpError(404, 'Not Found'))

    await expect(useIdpStepUp().start(7, 'idp_link', {})).rejects.toBeInstanceOf(HttpError)
    expect(sessionStorage.getItem(KEY)).toBeNull()
    expect(assign).not.toHaveBeenCalled()
    vi.unstubAllGlobals()
  })
})

describe('isIdpReauthRequired', () => {
  it('matches the problem type, not the status', () => {
    const type = 'urn:endurain:error:idp-reauth-required'
    expect(isIdpReauthRequired(new HttpError(401, 'Unauthorized', null, type))).toBe(true)
    expect(isIdpReauthRequired(new HttpError(401, 'Unauthorized'))).toBe(false)
    expect(isIdpReauthRequired(new Error('x'))).toBe(false)
  })
})
