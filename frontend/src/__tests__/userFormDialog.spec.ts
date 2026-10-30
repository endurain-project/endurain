import { flushPromises, mount } from '@vue/test-utils'
import { describe, expect, it, vi } from 'vitest'

import { QueryClient, VueQueryPlugin } from '@tanstack/vue-query'

import type { ManagedUser } from '@/features/users/types'

import { apiFetch } from '@/services/http'
import i18n from '@/i18n'
import UserFormDialog from '@/features/users/components/UserFormDialog.vue'

vi.mock('@/services/http', () => ({
  apiFetch: vi.fn<typeof apiFetch>(),
  HttpError: class extends Error {},
}))

const user: ManagedUser = {
  id: 1,
  version: 1,
  name: 'Admin',
  username: 'admin',
  email: 'admin@example.com',
  accessType: 'admin',
  active: true,
  emailVerified: true,
  pendingEmail: null,
  pendingEmailExpiresAt: null,
  pendingAdminApproval: false,
  mfaEnabled: false,
  externalAuthCount: 0,
  preferredLanguage: 'en',
  gender: 'unspecified',
  units: 'metric',
  currency: 'euro',
  firstDayOfWeek: 'monday',
  city: null,
  birthdate: null,
  height: null,
  maxHeartRate: null,
  photoPath: null,
  avatarUrl: null,
}

/** Passthrough stub so the reka-ui portal/focus-trap is skipped and the form
 * renders inline where the test can drive it. */
const passthrough = { template: '<div><slot /></div>' }

async function mountDialog(isSelf: boolean) {
  const wrapper = mount(UserFormDialog, {
    props: { open: false, user, isSelf },
    global: {
      plugins: [i18n, [VueQueryPlugin, { queryClient: new QueryClient() }]],
      stubs: {
        Dialog: passthrough,
        DialogContent: passthrough,
        DialogHeader: passthrough,
        DialogTitle: passthrough,
        DialogDescription: passthrough,
        DialogFooter: passthrough,
        RouterLink: { props: ['to'], template: '<a :data-to="to.name"><slot /></a>' },
      },
    },
  })
  // The form seeds itself when the dialog opens.
  await wrapper.setProps({ open: true })
  return wrapper
}

describe('UserFormDialog email field', () => {
  it('is editable when the administrator edits another user', async () => {
    const wrapper = await mountDialog(false)

    expect(wrapper.find('input[name="email"]').attributes('disabled')).toBeUndefined()
    expect(wrapper.find('a[data-to="settings-security"]').exists()).toBe(false)
  })

  it('is read-only and points to Security settings when the administrator edits themselves', async () => {
    // The admin route refuses a change to the caller's own email, which needs step-up.
    const wrapper = await mountDialog(true)

    const input = wrapper.find('input[name="email"]')
    expect(input.attributes('disabled')).toBeDefined()
    expect((input.element as HTMLInputElement).value).toBe('admin@example.com')
    expect(wrapper.find('a[data-to="settings-security"]').exists()).toBe(true)
  })
})

describe('UserFormDialog email verification switches', () => {
  const switches = (wrapper: Awaited<ReturnType<typeof mountDialog>>) =>
    wrapper.findAll<HTMLInputElement>('input[role="switch"]')

  it('shows a single editable verified switch while the email is unchanged', async () => {
    const wrapper = await mountDialog(false)

    expect(switches(wrapper)).toHaveLength(3)
    expect(wrapper.text()).not.toContain('Mark the new address as verified')
  })

  it('locks the current status and adds a new-address switch once the email changes', async () => {
    const wrapper = await mountDialog(false)
    await wrapper.find('input[name="email"]').setValue('new@example.com')

    const all = switches(wrapper)
    expect(all).toHaveLength(4)
    expect(all[1]!.element.disabled).toBe(true)
    expect(all[1]!.element.checked).toBe(true)
    expect(all[2]!.element.checked).toBe(false)
    expect(wrapper.text()).toContain('Mark the new address as verified')

    await wrapper.find('input[name="email"]').setValue('admin@example.com')
    expect(switches(wrapper)).toHaveLength(3)
  })

  it('sends the new-address switch as the payload emailVerified', async () => {
    vi.mocked(apiFetch).mockResolvedValue({ ...user })
    const wrapper = await mountDialog(false)
    await wrapper.find('input[name="email"]').setValue('new@example.com')
    await switches(wrapper)[2]!.setValue(true)
    await wrapper.find('form').trigger('submit')
    await flushPromises()

    const [, init] = vi.mocked(apiFetch).mock.calls.slice(-1)[0]!
    expect(JSON.parse(String(init?.body))).toMatchObject({
      email: 'new@example.com',
      email_verified: true,
    })
  })
})
