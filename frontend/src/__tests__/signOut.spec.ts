import { beforeEach, describe, expect, it, vi } from 'vitest'

import { useSignOut } from '@/features/auth/composables/useSignOut'

const logout = vi.fn<() => Promise<string | null>>()
const push = vi.fn<(location: unknown) => Promise<void>>()
const assign = vi.fn<(url: string) => void>()

vi.mock('@/features/auth/stores/auth', () => ({
  useAuthStore: () => ({ logout }),
}))

vi.mock('vue-router', () => ({
  useRouter: () => ({ push }),
}))

describe('useSignOut', () => {
  beforeEach(() => {
    vi.resetAllMocks()
    push.mockResolvedValue()
    vi.stubGlobal('location', { assign })
  })

  it('sends the browser to the provider when logout names its end-session URL', async () => {
    logout.mockResolvedValue('https://idp.example.com/logout?id_token_hint=abc')

    await useSignOut().signOut()

    expect(assign).toHaveBeenCalledWith('https://idp.example.com/logout?id_token_hint=abc')
    expect(push).not.toHaveBeenCalled()
  })

  it('shows the login page when there is no provider URL', async () => {
    logout.mockResolvedValue(null)

    await useSignOut().signOut()

    expect(assign).not.toHaveBeenCalled()
    expect(push).toHaveBeenCalledWith({ name: 'login', query: { logoutSuccess: 'true' } })
  })
})
