import { describe, expect, it, vi } from 'vitest'

import { useLoginRouteMessages } from '@/features/auth/composables/useLoginRouteMessages'

const mocks = vi.hoisted(() => ({
  route: { query: {} as Record<string, unknown> },
}))

vi.mock('vue-router', () => ({
  useRoute: () => mocks.route,
}))

vi.mock('vue-i18n', () => ({
  useI18n: () => ({ t: (key: string) => key }),
}))

describe('useLoginRouteMessages', () => {
  it('names a missing provider email instead of a generic SSO failure', () => {
    mocks.route.query = { error: 'sso_email_missing' }

    expect(useLoginRouteMessages().resolveInitialAlert()).toEqual({
      kind: 'error',
      message: 'login.ssoEmailMissing',
    })
  })

  it('falls back to the generic message for an unknown SSO error', () => {
    mocks.route.query = { error: 'something_else' }

    expect(useLoginRouteMessages().resolveInitialAlert()).toEqual({
      kind: 'error',
      message: 'login.ssoErrorUndefined',
    })
  })
})
