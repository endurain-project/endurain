import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { ref } from 'vue'
import { QueryClient, VueQueryPlugin } from '@tanstack/vue-query'

import i18n from '@/i18n'
import DeleteAccountCard from '@/features/security/components/DeleteAccountCard.vue'
import { HttpError } from '@/services/http'

const mocks = vi.hoisted(() => ({
  mutate: vi.fn<(input: unknown, options: { onError: (e: unknown) => void }) => void>(),
  toastError: vi.fn<(message: string) => void>(),
}))

vi.mock('@/composables/useToasts', () => ({
  useToasts: () => ({ success: vi.fn<() => void>(), error: mocks.toastError }),
}))
vi.mock('@/features/security/composables/useSecurity', () => ({
  useDeleteAccountMutation: () => ({ mutate: mocks.mutate, isPending: ref(false) }),
}))

/** Mounts the card with the step-up dialog replaced by a button that confirms it. */
function mountCard() {
  return mount(DeleteAccountCard, {
    props: { username: 'bob', hasLocalPassword: true, mfaEnabled: false, resume: null },
    global: {
      plugins: [i18n, [VueQueryPlugin, { queryClient: new QueryClient() }]],
      stubs: {
        StepUpDialog: {
          emits: ['confirm'],
          template:
            '<button data-test="confirm" @click="$emit(\'confirm\', { currentPassword: \'pw\', mfaCode: null })" />',
        },
      },
    },
  })
}

/** Confirms the deletion and fails it with the given error. */
async function failWith(error: unknown): Promise<void> {
  await mountCard().get('[data-test="confirm"]').trigger('click')
  mocks.mutate.mock.calls[0]![1].onError(error)
  await flushPromises()
}

describe('DeleteAccountCard refusals', () => {
  beforeEach(() => {
    mocks.mutate.mockReset()
    mocks.toastError.mockReset()
  })

  it('tells the only administrator to hand over the role first', async () => {
    await failWith(new HttpError(409, 'Conflict', null, 'urn:endurain:error:last-administrator'))

    expect(mocks.toastError).toHaveBeenCalledWith(
      i18n.global.t('settings.security.deleteAccount.onlyAdminError'),
    )
  })

  it('tells the user a deletion is already in progress for any other conflict', async () => {
    await failWith(new HttpError(409, 'Conflict', null, 'urn:endurain:error:conflict'))

    expect(mocks.toastError).toHaveBeenCalledWith(
      i18n.global.t('settings.security.deleteAccount.pendingError'),
    )
  })
})
