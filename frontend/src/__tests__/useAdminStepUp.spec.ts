import { describe, expect, it, vi } from 'vitest'
import { ref } from 'vue'

import { useAdminStepUp } from '@/features/security/composables/useAdminStepUp'

const mocks = vi.hoisted(() => ({
  profile: null as { hasLocalPassword: boolean; mfaEnabled: boolean } | null,
}))

vi.mock('@/features/profile/composables/useProfile', () => ({
  useProfileQuery: () => ({ data: ref(mocks.profile) }),
}))

describe('useAdminStepUp', () => {
  it.each([true, false])(
    'asks for an MFA code as the profile says (mfaEnabled %s)',
    (mfaEnabled) => {
      mocks.profile = { hasLocalPassword: true, mfaEnabled }

      expect(useAdminStepUp().requireMfa.value).toBe(mfaEnabled)
    },
  )
})
