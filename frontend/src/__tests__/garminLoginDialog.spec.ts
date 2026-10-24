import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { computed, nextTick, ref, type Ref } from 'vue'
import { mount } from '@vue/test-utils'

import type { GarminLinkStatus } from '@/features/integrations/types'

import i18n from '@/i18n'
import GarminLoginDialog from '@/features/integrations/components/GarminLoginDialog.vue'

const linkMutate = vi.fn<(input: unknown, options: { onSuccess?: () => void }) => void>()
const mfaMutate = vi.fn<(code: string) => void>()
const toastSuccess = vi.fn<(message: string) => void>()
const toastError = vi.fn<(message: string) => void>()
const statusData = ref<GarminLinkStatus | undefined>(undefined)
const statusError = ref(false)
let followed: Ref<boolean>

vi.mock('@/composables/useToasts', () => ({
  useToasts: () => ({ success: toastSuccess, error: toastError }),
}))

vi.mock('@/features/integrations/composables/useIntegrations', () => ({
  useLinkGarminMutation: () => ({ mutate: linkMutate, isPending: computed(() => false) }),
  useSubmitGarminMfaMutation: () => ({ mutate: mfaMutate }),
  useGarminLinkStatusQuery: (enabled: Ref<boolean>) => {
    followed = enabled
    return { data: statusData, isError: statusError }
  },
}))

/** Passthrough stub so the reka-ui portal/focus-trap is skipped and the form renders inline. */
const passthrough = { template: '<div><slot /></div>' }

const mounted: Array<{ unmount: () => void }> = []

async function mountDialog() {
  const wrapper = mount(GarminLoginDialog, {
    props: { open: false },
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
  await wrapper.setProps({ open: true })
  return wrapper
}

/** Fills the credentials and submits, then lets the start request be accepted. */
async function startLink(wrapper: Awaited<ReturnType<typeof mountDialog>>) {
  await wrapper.find('#garmin-username').setValue(' rider ')
  await wrapper.find('#garmin-password').setValue('pw')
  await wrapper.find('form').trigger('submit')
  linkMutate.mock.calls[0]?.[1].onSuccess?.()
  await nextTick()
}

describe('GarminLoginDialog', () => {
  afterEach(() => {
    // The mocked status refs are shared, so a dialog left mounted would keep reacting.
    mounted.splice(0).forEach((wrapper) => wrapper.unmount())
  })

  beforeEach(() => {
    vi.clearAllMocks()
    statusData.value = undefined
    statusError.value = false
  })

  it('starts the link with the trimmed credentials and then follows its status', async () => {
    const wrapper = await mountDialog()
    expect(followed.value).toBe(false)

    await startLink(wrapper)

    expect(linkMutate.mock.calls[0]?.[0]).toEqual({
      username: 'rider',
      password: 'pw',
      isCn: false,
    })
    expect(followed.value).toBe(true)
  })

  it('asks for the MFA code only once the status says so', async () => {
    const wrapper = await mountDialog()
    await startLink(wrapper)
    expect(wrapper.find('#garmin-mfa').exists()).toBe(false)

    statusData.value = { status: 'mfa_required', reason: null }
    await nextTick()

    expect(wrapper.find('#garmin-mfa').exists()).toBe(true)
    await wrapper.find('#garmin-mfa').setValue(' 123456 ')
    await wrapper.find('#garmin-mfa').element.closest('div')?.querySelector('button')?.click()
    expect(mfaMutate.mock.calls[0]?.[0]).toBe('123456')
  })

  it('closes with a success toast when the link completes', async () => {
    const wrapper = await mountDialog()
    await startLink(wrapper)

    statusData.value = { status: 'completed', reason: null }
    await nextTick()

    expect(toastSuccess).toHaveBeenCalledTimes(1)
    expect(wrapper.emitted('update:open')?.slice(-1)[0]).toEqual([false])
    expect(followed.value).toBe(false)
  })

  it.each(['invalid_credentials', 'incorrect_mfa', 'internal'] as const)(
    'reports a %s failure and lets the user retry',
    async (reason) => {
      const wrapper = await mountDialog()
      await startLink(wrapper)

      statusData.value = { status: 'failed', reason }
      await nextTick()

      expect(toastError).toHaveBeenCalledTimes(1)
      expect(followed.value).toBe(false)
      expect(wrapper.emitted('update:open')).toBeUndefined()
    },
  )

  it('stops waiting when the status can no longer be read', async () => {
    const wrapper = await mountDialog()
    await startLink(wrapper)

    statusError.value = true
    await nextTick()

    expect(toastError).toHaveBeenCalledTimes(1)
    expect(followed.value).toBe(false)
  })

  it('stops following when the dialog is closed mid-attempt', async () => {
    const wrapper = await mountDialog()
    await startLink(wrapper)

    await wrapper.setProps({ open: false })

    expect(followed.value).toBe(false)
  })
})
