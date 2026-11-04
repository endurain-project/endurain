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
  weightUnits: null,
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

async function mountDialog(isSelf: boolean, edited: ManagedUser = user) {
  const wrapper = mount(UserFormDialog, {
    props: { open: false, user: edited, isSelf },
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

/**
 * Waits for the user update request and returns its JSON body. The save is looked up by method rather
 * than taken as the last call, because a successful save refetches the users afterwards.
 */
async function sentUpdate(): Promise<unknown> {
  await vi.waitFor(() =>
    expect(apiFetch).toHaveBeenCalledWith('/users/1', expect.objectContaining({ method: 'PUT' })),
  )
  const [, init] = vi.mocked(apiFetch).mock.calls.find(([, i]) => i?.method === 'PUT')!
  return JSON.parse(String(init?.body))
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
    vi.mocked(apiFetch).mockClear()
    vi.mocked(apiFetch).mockResolvedValue({ ...user })
    const wrapper = await mountDialog(false)
    await wrapper.find('input[name="email"]').setValue('new@example.com')
    await switches(wrapper)[2]!.setValue(true)
    await wrapper.find('form').trigger('submit')

    expect(await sentUpdate()).toMatchObject({
      email: 'new@example.com',
      email_verified: true,
    })
  })
})

describe('UserFormDialog weight units', () => {
  const weightUnitsSelect = (wrapper: Awaited<ReturnType<typeof mountDialog>>) =>
    wrapper.findAll('select').find((select) => select.find('option[value="default"]').exists())!

  it('seeds the override and sends it back unchanged', async () => {
    vi.mocked(apiFetch).mockClear()
    vi.mocked(apiFetch).mockResolvedValue({ ...user })
    const wrapper = await mountDialog(false, { ...user, weightUnits: 'imperial' })

    expect((weightUnitsSelect(wrapper).element as HTMLSelectElement).value).toBe('imperial')
    await wrapper.find('input[name="name"]').setValue('Renamed')
    await wrapper.find('form').trigger('submit')

    expect(await sentUpdate()).toMatchObject({ weight_units: 'imperial' })
  })

  it('sends null when set to follow units', async () => {
    vi.mocked(apiFetch).mockClear()
    vi.mocked(apiFetch).mockResolvedValue({ ...user })
    const wrapper = await mountDialog(false, { ...user, weightUnits: 'imperial' })

    await weightUnitsSelect(wrapper).setValue('default')
    await wrapper.find('form').trigger('submit')

    expect(await sentUpdate()).toMatchObject({ weight_units: null })
  })
})

describe('UserFormDialog height', () => {
  const unitsSelect = (wrapper: Awaited<ReturnType<typeof mountDialog>>) =>
    wrapper
      .findAll('select')
      .find(
        (select) =>
          select.find('option[value="imperial"]').exists() &&
          !select.find('option[value="default"]').exists(),
      )!

  it('keeps a height that is not a whole number of inches when only the units change', async () => {
    // Regression: 172 cm displays as 5 ft 8 in, which converted back to 173 cm on save.
    vi.mocked(apiFetch).mockResolvedValue({ ...user })
    const wrapper = await mountDialog(false, { ...user, height: 172 })
    vi.mocked(apiFetch).mockClear()

    await unitsSelect(wrapper).setValue('imperial')
    await wrapper.find('form').trigger('submit')

    expect(await sentUpdate()).toMatchObject({ units: 'imperial', height: 172 })
  })

  it.each(['0', '400'])('rejects a height of %s cm and does not submit', async (cm) => {
    vi.mocked(apiFetch).mockClear()
    const wrapper = await mountDialog(false)

    const height = wrapper.find('input[name="heightCm"]')
    await height.setValue(cm)
    await height.trigger('blur')

    expect(wrapper.text()).toContain(i18n.global.t('settings.users.form.heightInvalid'))
    await wrapper.find('form').trigger('submit')
    await flushPromises()
    expect(apiFetch).not.toHaveBeenCalledWith(
      '/users/1',
      expect.objectContaining({ method: 'PUT' }),
    )
  })

  it.each(['10', '300'])('rejects a max heart rate of %s bpm and does not submit', async (bpm) => {
    vi.mocked(apiFetch).mockClear()
    const wrapper = await mountDialog(false)

    const maxHeartRate = wrapper.find('input[name="maxHeartRate"]')
    await maxHeartRate.setValue(bpm)
    await maxHeartRate.trigger('blur')

    expect(wrapper.text()).toContain(i18n.global.t('settings.users.form.maxHeartRateInvalid'))
    await wrapper.find('form').trigger('submit')
    await flushPromises()
    expect(apiFetch).not.toHaveBeenCalledWith(
      '/users/1',
      expect.objectContaining({ method: 'PUT' }),
    )
  })
})
