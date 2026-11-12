import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { ref } from 'vue'

import { QueryClient, VueQueryPlugin } from '@tanstack/vue-query'

import type { IdpStepUpResume } from '@/features/security/composables/useIdpStepUp'
import type { ManagedUser } from '@/features/users/types'

import { apiFetch } from '@/services/http'
import i18n from '@/i18n'
import { queryKeys } from '@/services/queryKeys'
import UserFormDialog from '@/features/users/components/UserFormDialog.vue'

vi.mock('@/services/http', () => ({
  apiFetch: vi.fn<typeof apiFetch>(),
  HttpError: class extends Error {},
}))

vi.mock('@/features/security/composables/useAdminStepUp', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/features/security/composables/useAdminStepUp')>()),
  useAdminStepUp: () => ({ requirePassword: ref(true), requireMfa: ref(false) }),
}))

// The form reads the mail settings through a store-backed query.
beforeEach(() => {
  setActivePinia(createPinia())
})

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
  deletionRequestedAt: null,
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

const stubs = {
  Dialog: passthrough,
  DialogContent: passthrough,
  DialogHeader: passthrough,
  DialogTitle: passthrough,
  DialogDescription: passthrough,
  DialogFooter: passthrough,
  RouterLink: { props: ['to'], template: '<a :data-to="to.name"><slot /></a>' },
}

type Wrapper = Awaited<ReturnType<typeof mountDialog>>

/** Fills the administrator's password in the step-up dialog and confirms it. */
async function confirmStepUp(wrapper: Wrapper): Promise<void> {
  await flushPromises()
  await wrapper.get('#stepup-password').setValue('admin-pw')
  await wrapper.findAll('form')[1]!.trigger('submit')
}

async function mountDialog(
  isSelf: boolean,
  edited: ManagedUser = user,
  queryClient = new QueryClient(),
) {
  const wrapper = mount(UserFormDialog, {
    props: { open: false, user: edited, isSelf },
    global: {
      plugins: [i18n, [VueQueryPlugin, { queryClient }]],
      stubs,
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
    expect(apiFetch).toHaveBeenCalledWith('/users/1', expect.objectContaining({ method: 'PATCH' })),
  )
  const [, init] = vi.mocked(apiFetch).mock.calls.find(([, i]) => i?.method === 'PATCH')!
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

    expect(switches(wrapper)).toHaveLength(2)
    expect(wrapper.text()).not.toContain('Mark the new address as verified')
  })

  it('locks the current status and adds a new-address switch once the email changes', async () => {
    const wrapper = await mountDialog(false)
    await wrapper.find('input[name="email"]').setValue('new@example.com')

    const all = switches(wrapper)
    expect(all).toHaveLength(3)
    expect(all[1]!.element.disabled).toBe(true)
    expect(all[1]!.element.checked).toBe(true)
    expect(all[2]!.element.checked).toBe(false)
    expect(wrapper.text()).toContain('Mark the new address as verified')

    await wrapper.find('input[name="email"]').setValue('admin@example.com')
    expect(switches(wrapper)).toHaveLength(2)
  })

  it('sends the new-address switch as the payload emailVerified', async () => {
    vi.mocked(apiFetch).mockClear()
    vi.mocked(apiFetch).mockResolvedValue({ ...user })
    const wrapper = await mountDialog(false)
    await wrapper.find('input[name="email"]').setValue('new@example.com')
    await switches(wrapper)[2]!.setValue(true)
    await wrapper.find('form').trigger('submit')
    await confirmStepUp(wrapper)

    expect(await sentUpdate()).toMatchObject({
      email: 'new@example.com',
      email_verified: true,
    })
  })
})

describe('UserFormDialog step-up', () => {
  /** The step-up dialog renders as the second form of the stubbed dialogs. */
  const stepUpPatches = () =>
    vi.mocked(apiFetch).mock.calls.filter(([, init]) => init?.method === 'PATCH')

  it.each([
    ['email', async (w: Wrapper) => w.find('input[name="email"]').setValue('new@example.com')],
    [
      'access type',
      async (w: Wrapper) =>
        w
          .findAll('select')
          .find((select) => select.find('option[value="admin"]').exists())!
          .setValue('regular'),
    ],
    ['active flag', async (w: Wrapper) => w.find('input[role="switch"]').setValue(false)],
  ])('asks for the administrator step-up before saving a changed %s', async (_label, change) => {
    vi.mocked(apiFetch).mockClear()
    vi.mocked(apiFetch).mockResolvedValue({ ...user })
    const wrapper = await mountDialog(false)
    await change(wrapper)
    await wrapper.find('form').trigger('submit')
    await flushPromises()

    expect(stepUpPatches()).toHaveLength(0)

    await confirmStepUp(wrapper)
    const body = (await sentUpdate()) as { step_up?: unknown }
    expect(body.step_up).toEqual({ current_password: 'admin-pw', mfa_code: null })
  })

  it('saves without a step-up when no sensitive field changed', async () => {
    vi.mocked(apiFetch).mockClear()
    vi.mocked(apiFetch).mockResolvedValue({ ...user })
    const wrapper = await mountDialog(false)
    await wrapper.find('input[name="name"]').setValue('Renamed')
    await wrapper.find('form').trigger('submit')

    expect(await sentUpdate()).not.toHaveProperty('step_up')
  })

  it('reopens the step-up with the draft restored after an identity-provider return', async () => {
    vi.mocked(apiFetch).mockClear()
    vi.mocked(apiFetch).mockResolvedValue({ ...user })
    const wrapper = mount(UserFormDialog, {
      props: {
        open: false,
        user,
        resume: {
          action: 'admin_user_edit',
          reauth: { ticket: 't1', codeVerifier: 'v1' },
          pending: {
            userId: user.id,
            draft: { name: 'Draft name', email: 'draft@example.com', password: 'ignored' },
          },
        },
      },
      global: { plugins: [i18n, [VueQueryPlugin, { queryClient: new QueryClient() }]], stubs },
    })
    await flushPromises()

    expect(wrapper.emitted('update:open')?.[0]).toEqual([true])
    await wrapper.setProps({ open: true })
    await flushPromises()
    expect((wrapper.find('input[name="name"]').element as HTMLInputElement).value).toBe(
      'Draft name',
    )
    expect((wrapper.find('input[name="email"]').element as HTMLInputElement).value).toBe(
      'draft@example.com',
    )
  })
})

describe('UserFormDialog weight units', () => {
  const weightUnitsSelect = (wrapper: Awaited<ReturnType<typeof mountDialog>>) =>
    wrapper.findAll('select').find((select) => select.find('option[value="default"]').exists())!

  it('seeds the override and leaves it out of an edit that keeps it', async () => {
    vi.mocked(apiFetch).mockClear()
    vi.mocked(apiFetch).mockResolvedValue({ ...user })
    const wrapper = await mountDialog(false, { ...user, weightUnits: 'imperial' })

    expect((weightUnitsSelect(wrapper).element as HTMLSelectElement).value).toBe('imperial')
    await wrapper.find('input[name="name"]').setValue('Renamed')
    await wrapper.find('form').trigger('submit')

    expect(await sentUpdate()).toEqual({ name: 'Renamed' })
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

describe('UserFormDialog health cache', () => {
  it("invalidates the health queries when the signed-in user's own height changes", async () => {
    vi.mocked(apiFetch).mockClear()
    vi.mocked(apiFetch).mockResolvedValue({ ...user })
    const queryClient = new QueryClient()
    queryClient.setQueryData(queryKeys.currentUser(), { id: user.id })
    const invalidate = vi.spyOn(queryClient, 'invalidateQueries')
    const wrapper = await mountDialog(true, { ...user, height: 170 }, queryClient)

    await wrapper.find('input[name="heightCm"]').setValue('180')
    await wrapper.find('form').trigger('submit')
    await sentUpdate()

    expect(invalidate).toHaveBeenCalledWith({ queryKey: queryKeys.health.all() })
  })

  it("leaves the health queries alone when another user's height changes", async () => {
    vi.mocked(apiFetch).mockClear()
    vi.mocked(apiFetch).mockResolvedValue({ ...user })
    const queryClient = new QueryClient()
    queryClient.setQueryData(queryKeys.currentUser(), { id: user.id + 1 })
    const invalidate = vi.spyOn(queryClient, 'invalidateQueries')
    const wrapper = await mountDialog(false, { ...user, height: 170 }, queryClient)

    await wrapper.find('input[name="heightCm"]').setValue('180')
    await wrapper.find('form').trigger('submit')
    await sentUpdate()
    await flushPromises()

    expect(invalidate).not.toHaveBeenCalledWith({ queryKey: queryKeys.health.all() })
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

    expect(await sentUpdate()).toEqual({ units: 'imperial' })
  })

  it.each(['49', '273'])('rejects a height of %s cm and does not submit', async (cm) => {
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
      expect.objectContaining({ method: 'PATCH' }),
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
      expect.objectContaining({ method: 'PATCH' }),
    )
  })
})

describe('UserFormDialog create step-up', () => {
  const PASSWORD = 'a-very-long-password-123'

  async function mountCreate(resume: IdpStepUpResume | null = null) {
    const wrapper = mount(UserFormDialog, {
      props: { open: false, user: null, resume },
      global: { plugins: [i18n, [VueQueryPlugin, { queryClient: new QueryClient() }]], stubs },
    })
    await wrapper.setProps({ open: true })
    await flushPromises()
    return wrapper
  }

  async function fillCreate(wrapper: Awaited<ReturnType<typeof mountCreate>>, accessType: string) {
    await wrapper.find('input[name="name"]').setValue('New')
    await wrapper.find('input[name="username"]').setValue('newuser')
    await wrapper.find('input[name="email"]').setValue('new@example.com')
    await wrapper.find('input[name="new-password"]').setValue(PASSWORD)
    await wrapper.find('input[name="confirm-password"]').setValue(PASSWORD)
    await wrapper
      .findAll('select')
      .find((select) => select.find('option[value="admin"]').exists())!
      .setValue(accessType)
    await wrapper.find('form').trigger('submit')
    await flushPromises()
  }

  const createPosts = () =>
    vi
      .mocked(apiFetch)
      .mock.calls.filter(([path, init]) => path === '/users' && init?.method === 'POST')

  it('asks for the administrator step-up before creating an administrator', async () => {
    vi.mocked(apiFetch).mockClear()
    vi.mocked(apiFetch).mockResolvedValue({ ...user })
    const wrapper = await mountCreate()
    await fillCreate(wrapper, 'admin')

    expect(createPosts()).toHaveLength(0)

    await confirmStepUp(wrapper)
    await vi.waitFor(() => expect(createPosts()).toHaveLength(1))
    const body = JSON.parse(String(createPosts()[0]![1]?.body)) as { step_up?: unknown }
    expect(body.step_up).toEqual({ current_password: 'admin-pw', mfa_code: null })
  })

  it('creates a regular account without a step-up', async () => {
    vi.mocked(apiFetch).mockClear()
    vi.mocked(apiFetch).mockResolvedValue({ ...user })
    const wrapper = await mountCreate()
    await fillCreate(wrapper, 'regular')

    await vi.waitFor(() => expect(createPosts()).toHaveLength(1))
    expect(JSON.parse(String(createPosts()[0]![1]?.body))).not.toHaveProperty('step_up')
  })

  it('reopens the form with the draft after an identity-provider return, without the passwords', async () => {
    const wrapper = await mountCreate({
      action: 'admin_user_create',
      reauth: { ticket: 't1', codeVerifier: 'v1' },
      pending: { create: true, draft: { name: 'Draft', accessType: 'admin', password: PASSWORD } },
    })

    expect(wrapper.emitted('update:open')?.[0]).toEqual([true])
    expect((wrapper.find('input[name="name"]').element as HTMLInputElement).value).toBe('Draft')
    expect((wrapper.find('input[name="new-password"]').element as HTMLInputElement).value).toBe('')
  })

  it('keeps the pending context free of the passwords', async () => {
    const wrapper = await mountCreate()
    await wrapper.find('input[name="new-password"]').setValue(PASSWORD)
    await wrapper.find('input[name="confirm-password"]').setValue(PASSWORD)

    const context = wrapper.findComponent({ name: 'StepUpDialog' }).props('pendingContext')
    expect(JSON.stringify(context)).not.toContain(PASSWORD)
    expect(context).toMatchObject({ create: true })
  })

  it.each<[string, IdpStepUpResume['action'], Record<string, unknown>]>([
    ['an edit return', 'admin_user_edit', { userId: 1, draft: {} }],
    ['a return for another action', 'admin_credential_reset', { create: true, draft: {} }],
  ])('does not open the create form for %s', async (_label, action, pending) => {
    const wrapper = await mountCreate({
      action,
      reauth: { ticket: 't1', codeVerifier: 'v1' },
      pending,
    })

    expect(wrapper.emitted('update:open')).toBeUndefined()
  })

  it('does not open the edit form for a create return', async () => {
    const wrapper = mount(UserFormDialog, {
      props: {
        open: false,
        user,
        resume: {
          action: 'admin_user_edit',
          reauth: { ticket: 't1', codeVerifier: 'v1' },
          pending: { create: true, draft: {} },
        },
      },
      global: { plugins: [i18n, [VueQueryPlugin, { queryClient: new QueryClient() }]], stubs },
    })
    await flushPromises()

    expect(wrapper.emitted('update:open')).toBeUndefined()
  })
})

describe('UserFormDialog invitation', () => {
  const PASSWORD = 'a-very-long-password-123'

  /** Mounts the create form; the mail settings the form reads are seeded, so no request is made for them. */
  async function mountInvite(mailConfigured: boolean) {
    const queryClient = new QueryClient()
    queryClient.setQueryData(queryKeys.serverSettings.mail(), {
      version: 1,
      host: mailConfigured ? 'smtp.example.com' : null,
      port: 587,
      security: 'starttls',
      username: null,
      fromAddress: null,
      passwordSet: false,
      envManaged: {},
      emailStatus: { configured: mailConfigured, problems: [] },
    })
    const wrapper = mount(UserFormDialog, {
      props: { open: false, user: null },
      global: { plugins: [i18n, [VueQueryPlugin, { queryClient }]], stubs },
    })
    await wrapper.setProps({ open: true })
    await flushPromises()
    return wrapper
  }

  async function fillProfile(wrapper: Awaited<ReturnType<typeof mountInvite>>) {
    await wrapper.find('input[name="name"]').setValue('New')
    await wrapper.find('input[name="username"]').setValue('newuser')
    await wrapper.find('input[name="email"]').setValue('new@example.com')
  }

  const createBody = async (): Promise<Record<string, unknown>> => {
    const posts = () =>
      vi
        .mocked(apiFetch)
        .mock.calls.filter(([path, init]) => path === '/users' && init?.method === 'POST')
    await vi.waitFor(() => expect(posts()).toHaveLength(1))
    return JSON.parse(String(posts()[0]![1]?.body)) as Record<string, unknown>
  }

  it('defaults to an invitation and asks for no password when mail is configured', async () => {
    vi.mocked(apiFetch).mockClear()
    vi.mocked(apiFetch).mockResolvedValue({ ...user })
    const wrapper = await mountInvite(true)

    expect(wrapper.find('select[name="passwordMode"]').exists()).toBe(true)
    expect(wrapper.find('input[name="new-password"]').exists()).toBe(false)

    await fillProfile(wrapper)
    await wrapper.find('form').trigger('submit')

    expect(await createBody()).not.toHaveProperty('password')
  })

  it('sets a password when the administrator chooses to', async () => {
    vi.mocked(apiFetch).mockClear()
    vi.mocked(apiFetch).mockResolvedValue({ ...user })
    const wrapper = await mountInvite(true)
    await wrapper.find('select[name="passwordMode"]').setValue('password')
    await fillProfile(wrapper)
    await wrapper.find('input[name="new-password"]').setValue(PASSWORD)
    await wrapper.find('input[name="confirm-password"]').setValue(PASSWORD)
    await wrapper.find('form').trigger('submit')

    expect(await createBody()).toMatchObject({ password: PASSWORD })
  })

  it('offers no choice and asks for a password when mail is not configured', async () => {
    const wrapper = await mountInvite(false)

    expect(wrapper.find('select[name="passwordMode"]').exists()).toBe(false)
    expect(wrapper.find('input[name="new-password"]').exists()).toBe(true)
  })

  it('asks for a password for an inactive account, which an invitation cannot activate', async () => {
    const wrapper = await mountInvite(true)
    await wrapper.find('input[role="switch"]').setValue(false)

    expect(wrapper.find('input[name="new-password"]').exists()).toBe(true)
  })
})
