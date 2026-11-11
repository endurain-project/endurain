import { afterEach, describe, expect, it, vi } from 'vitest'
import { computed, nextTick, ref } from 'vue'
import { mount } from '@vue/test-utils'

import type { ProfileImportStatus } from '@/features/profile/types'
import type { IdpStepUpResume } from '@/features/security/composables/useIdpStepUp'

import i18n from '@/i18n'
import DataTransferCard from '@/features/profile/components/DataTransferCard.vue'
import { HttpError } from '@/services/http'

const importStatus = ref<ProfileImportStatus | null>(null)
const exportMutate = vi.fn<(...args: unknown[]) => void>()
const toastError = vi.fn<(message: string) => void>()
const toastSuccess = vi.fn<(message: string) => void>()
const challenge = vi.fn<(error: unknown) => boolean>()

vi.mock('@/composables/useToasts', () => ({
  useToasts: () => ({ success: toastSuccess, error: toastError }),
}))
vi.mock('@/features/security/composables/useIdpStepUp', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/features/security/composables/useIdpStepUp')>()),
  useIdpStepUp: () => ({ start: vi.fn<() => Promise<void>>() }),
  useIdpReauthChallenge: () => challenge,
}))
vi.mock('@/features/security/composables/useLinkedAccounts', () => ({
  useLinkedProvidersQuery: () => ({
    data: computed(() => []),
    isPending: computed(() => false),
    isError: computed(() => false),
  }),
}))
vi.mock('@/features/profile/composables/useDataTransfer', () => ({
  useExportProfileMutation: () => ({ mutate: exportMutate, isPending: ref(false) }),
  useDownloadProfileExportMutation: () => ({ mutate: vi.fn<() => void>(), isPending: ref(false) }),
  useImportProfileMutation: () => ({ mutate: vi.fn<() => void>(), isPending: ref(false) }),
  useProfileExportQuery: () => computed(() => null),
  useProfileImportQuery: () => computed(() => importStatus.value),
}))

const passthrough = { template: '<div><slot /></div>' }
const mounted: Array<{ unmount: () => void }> = []

function mountCard(
  props: { hasLocalPassword?: boolean; mfaEnabled?: boolean; resume?: IdpStepUpResume | null } = {},
) {
  const wrapper = mount(DataTransferCard, {
    props: { userId: 1, hasLocalPassword: true, mfaEnabled: false, resume: null, ...props },
    global: {
      plugins: [i18n],
      stubs: {
        Dialog: passthrough,
        DialogContent: passthrough,
        DialogHeader: passthrough,
        DialogTitle: passthrough,
        DialogDescription: passthrough,
        DialogFooter: passthrough,
      },
    },
  })
  mounted.push(wrapper)
  return wrapper
}

afterEach(() => {
  exportMutate.mockReset()
  toastError.mockReset()
  toastSuccess.mockReset()
  challenge.mockReset()
  mounted.splice(0).forEach((wrapper) => wrapper.unmount())
})

describe('DataTransferCard', () => {
  it('explains that an archive from a different account was refused', () => {
    importStatus.value = {
      status: 'failed',
      error_code: 'wrong_account',
      imported: null,
    } as ProfileImportStatus
    const wrapper = mountCard()

    expect(wrapper.get('[role="status"]').text()).toBe(
      "The import didn't complete: the archive was exported from a different account. Nothing was imported.",
    )
    importStatus.value = null
  })

  it('asks for step-up before queueing an export and sends the credentials with it', async () => {
    const wrapper = mountCard({ mfaEnabled: true })
    const exportButton = wrapper.findAll('button').find((b) => b.text() === 'Export data')
    await exportButton!.trigger('click')
    expect(exportMutate).not.toHaveBeenCalled()

    await wrapper.find('#stepup-password').setValue('pw')
    await wrapper.find('#stepup-mfa').setValue('123456')
    await wrapper.find('form').trigger('submit')

    expect(exportMutate.mock.calls[0]![0]).toEqual({
      currentPassword: 'pw',
      mfaCode: '123456',
      idpReauth: null,
    })
  })

  it('reopens the dialog with the proof when the identity-provider sign-in returns', async () => {
    const wrapper = mountCard({
      hasLocalPassword: false,
      resume: { action: 'profile_export', reauth: { ticket: 't', codeVerifier: 'v' }, pending: {} },
    })
    await nextTick()

    await wrapper.find('form').trigger('submit')

    expect(exportMutate.mock.calls[0]![0]).toEqual({
      currentPassword: null,
      mfaCode: null,
      idpReauth: { ticket: 't', codeVerifier: 'v' },
    })
  })

  it('ignores a resume that was started for another operation', async () => {
    const wrapper = mountCard({
      hasLocalPassword: false,
      resume: { action: 'account_delete', reauth: { ticket: 't', codeVerifier: 'v' }, pending: {} },
    })
    await nextTick()

    expect(wrapper.find('button[type="submit"]').attributes('disabled')).toBeDefined()
  })

  it('reports a refused step-up as wrong credentials and any other failure as an export error', async () => {
    const wrapper = mountCard()
    await wrapper
      .findAll('button')
      .find((b) => b.text() === 'Export data')!
      .trigger('click')
    await wrapper.find('#stepup-password').setValue('pw')
    await wrapper.find('form').trigger('submit')
    const onError = (exportMutate.mock.calls[0]![1] as { onError: (e: unknown) => void }).onError

    challenge.mockReturnValue(false)
    onError(new HttpError(403, 'Forbidden', null, 'urn:endurain:error:step-up-failed'))
    onError(new Error('boom'))

    expect(toastError.mock.calls.map((call) => call[0])).toEqual([
      'Your password or code is incorrect.',
      "Couldn't start the export. Please try again.",
    ])
  })

  it('leaves the error to the identity-provider challenge handler when it takes it', async () => {
    const wrapper = mountCard()
    await wrapper
      .findAll('button')
      .find((b) => b.text() === 'Export data')!
      .trigger('click')
    await wrapper.find('#stepup-password').setValue('pw')
    await wrapper.find('form').trigger('submit')
    const onError = (exportMutate.mock.calls[0]![1] as { onError: (e: unknown) => void }).onError

    challenge.mockReturnValue(true)
    onError(new HttpError(403, 'Forbidden', null, 'urn:endurain:error:step-up-failed'))

    expect(toastError).not.toHaveBeenCalled()
  })
})
