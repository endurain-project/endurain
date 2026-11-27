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

  it('tells the user to sign in locally when the provider does not link by email', () => {
    mocks.route.query = { error: 'sso_link_by_email_disabled' }

    expect(useLoginRouteMessages().resolveInitialAlert()).toEqual({
      kind: 'error',
      message: 'login.ssoLinkByEmailDisabled',
    })
  })

  it('tells a new SSO account to wait for administrator approval, as information', () => {
    mocks.route.query = { error: 'sso_approval_pending' }

    expect(useLoginRouteMessages().resolveInitialAlert()).toEqual({
      kind: 'info',
      message: 'login.adminApprovalRequired',
    })
  })

  it('names an inactive account instead of a generic SSO failure', () => {
    mocks.route.query = { error: 'sso_account_disabled' }

    expect(useLoginRouteMessages().resolveInitialAlert()).toEqual({
      kind: 'error',
      message: 'login.ssoAccountDisabled',
    })
  })

  it('names an address the provider did not verify', () => {
    mocks.route.query = { error: 'sso_email_unverified' }

    expect(useLoginRouteMessages().resolveInitialAlert()).toEqual({
      kind: 'error',
      message: 'login.ssoEmailUnverified',
    })
  })

  it('falls back to the generic message for an unknown SSO error', () => {
    mocks.route.query = { error: 'something_else' }

    expect(useLoginRouteMessages().resolveInitialAlert()).toEqual({
      kind: 'error',
      message: 'login.ssoErrorUndefined',
    })
  })

  it('says both when verification and administrator approval are pending', () => {
    mocks.route.query = { emailVerificationSent: 'true', adminApprovalRequired: 'true' }

    expect(useLoginRouteMessages().resolveInitialAlert()).toEqual({
      kind: 'info',
      message: 'login.emailVerificationAndApprovalRequired',
    })
  })

  it('keeps the single-flag messages', () => {
    mocks.route.query = { adminApprovalRequired: 'true' }

    expect(useLoginRouteMessages().resolveInitialAlert()?.message).toBe(
      'login.adminApprovalRequired',
    )
  })
})
