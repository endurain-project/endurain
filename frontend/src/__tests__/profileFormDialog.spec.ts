import { flushPromises, mount } from '@vue/test-utils'
import { describe, expect, it, vi } from 'vitest'

import { QueryClient, VueQueryPlugin } from '@tanstack/vue-query'

import type { ProfileDetails } from '@/features/profile/types'

import { apiFetch } from '@/services/http'
import i18n from '@/i18n'
import ProfileFormDialog from '@/features/profile/components/ProfileFormDialog.vue'

vi.mock('@/services/http', () => ({
  apiFetch: vi.fn<typeof apiFetch>(),
  HttpError: class extends Error {},
}))

const profile: ProfileDetails = {
  id: 1,
  version: 1,
  name: 'Tester',
  username: 'tester',
  email: 'tester@example.com',
  pendingEmail: null,
  pendingEmailExpiresAt: null,
  city: null,
  birthdate: null,
  gender: 'unspecified',
  units: 'metric',
  weightUnits: null,
  currency: 'euro',
  height: 172,
  maxHeartRate: null,
  preferredLanguage: 'en',
  firstDayOfWeek: 'monday',
  timezone: 'UTC',
  accessType: 'regular',
  hasLocalPassword: true,
  mfaEnabled: false,
  integrationsVersion: 1,
  stravaLinked: false,
  stravaRevokedAt: null,
  stravaDataDeletionAt: null,
  garminLinked: false,
  photoPath: null,
  avatarUrl: null,
  privacy: {} as ProfileDetails['privacy'],
}

/** Passthrough stub so the reka-ui portal/focus-trap is skipped and the form renders inline. */
const passthrough = { template: '<div><slot /></div>' }

async function mountDialog(edited: ProfileDetails = profile) {
  const wrapper = mount(ProfileFormDialog, {
    props: { open: false, profile: edited },
    global: {
      plugins: [i18n, [VueQueryPlugin, { queryClient: new QueryClient() }]],
      stubs: {
        Dialog: passthrough,
        DialogContent: passthrough,
        DialogHeader: passthrough,
        DialogTitle: passthrough,
        DialogDescription: passthrough,
        DialogFooter: passthrough,
        RouterLink: { props: ['to'], template: '<a><slot /></a>' },
      },
    },
  })
  // The form seeds itself when the dialog opens.
  await wrapper.setProps({ open: true })
  return wrapper
}

async function saveBody(wrapper: Awaited<ReturnType<typeof mountDialog>>) {
  vi.mocked(apiFetch).mockClear()
  await wrapper.find('form').trigger('submit')
  // Wait for the save request itself rather than assuming it is the last call made.
  await vi.waitFor(() =>
    expect(apiFetch).toHaveBeenCalledWith('/profile', expect.objectContaining({ method: 'PATCH' })),
  )
  await flushPromises()
  const [, init] = vi.mocked(apiFetch).mock.calls.find(([, i]) => i?.method === 'PATCH')!
  return JSON.parse(String(init?.body)) as Record<string, unknown>
}

describe('ProfileFormDialog height', () => {
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
    vi.mocked(apiFetch).mockResolvedValue({ ...profile })
    const wrapper = await mountDialog()

    await unitsSelect(wrapper).setValue('imperial')

    expect(await saveBody(wrapper)).toMatchObject({ units: 'imperial', height: 172 })
  })

  it('keeps the height on a later save while imperial is already selected', async () => {
    vi.mocked(apiFetch).mockResolvedValue({ ...profile })
    const wrapper = await mountDialog({ ...profile, units: 'imperial' })
    await wrapper.find('input[name="name"]').setValue('Renamed')

    expect(await saveBody(wrapper)).toMatchObject({ units: 'imperial', height: 172 })
  })

  it('converts the feet and inches the user edits', async () => {
    vi.mocked(apiFetch).mockResolvedValue({ ...profile })
    const wrapper = await mountDialog({ ...profile, units: 'imperial' })

    await wrapper.find('input[name="heightInches"]').setValue('9')

    expect(await saveBody(wrapper)).toMatchObject({ height: 175 })
  })
})

describe('ProfileFormDialog username', () => {
  it('has no username field and never sends one, as it is changed in the security settings', async () => {
    vi.mocked(apiFetch).mockResolvedValue({ ...profile })
    const wrapper = await mountDialog()
    await wrapper.find('input[name="name"]').setValue('Renamed')

    expect(wrapper.find('input[name="username"]').exists()).toBe(false)
    expect(await saveBody(wrapper)).not.toHaveProperty('username')
  })
})

describe('ProfileFormDialog number validation', () => {
  it('rejects a metric height outside 50-272 cm and blocks saving', async () => {
    const wrapper = await mountDialog()
    const height = wrapper.find('input[name="heightCm"]')

    await height.setValue('273')
    await height.trigger('blur')

    expect(wrapper.text()).toContain(i18n.global.t('settings.users.form.heightInvalid'))
    expect(wrapper.find('button[type="submit"]').attributes('disabled')).toBeDefined()
  })

  it('rejects a metric height below 50 cm', async () => {
    const wrapper = await mountDialog()
    const height = wrapper.find('input[name="heightCm"]')

    await height.setValue('49')
    await height.trigger('blur')

    expect(wrapper.text()).toContain(i18n.global.t('settings.users.form.heightInvalid'))
  })

  it('rejects a maximum heart rate outside 30-250 bpm', async () => {
    const wrapper = await mountDialog()
    const heartRate = wrapper.find('input[name="maxHeartRate"]')

    await heartRate.setValue('20')
    await heartRate.trigger('blur')

    expect(wrapper.text()).toContain(i18n.global.t('settings.users.form.maxHeartRateInvalid'))
  })

  it('accepts values on the limits', async () => {
    const wrapper = await mountDialog()

    await wrapper.find('input[name="heightCm"]').setValue('272')
    await wrapper.find('input[name="maxHeartRate"]').setValue('30')
    await wrapper.find('input[name="maxHeartRate"]').trigger('blur')

    expect(wrapper.text()).not.toContain(i18n.global.t('settings.users.form.maxHeartRateInvalid'))
    expect(wrapper.find('button[type="submit"]').attributes('disabled')).toBeUndefined()
  })
})

describe('ProfileFormDialog timezone', () => {
  const browserTimezone = Intl.DateTimeFormat().resolvedOptions().timeZone || 'UTC'
  const unsetProfile: ProfileDetails = { ...profile, timezone: null }

  it('keeps an unset timezone unset on save', async () => {
    const wrapper = await mountDialog(unsetProfile)
    await wrapper.find('input[name="name"]').setValue('Renamed')

    expect((await saveBody(wrapper)).timezone).toBeNull()
  })

  it('sets the browser timezone when the user picks the browser action', async () => {
    const wrapper = await mountDialog(unsetProfile)
    const action = wrapper
      .findAll('button[type="button"]')
      .find((button) => button.text().includes(browserTimezone))!

    await action.trigger('click')

    expect((await saveBody(wrapper)).timezone).toBe(browserTimezone)
  })
})

describe('ProfileFormDialog unchanged save', () => {
  it('sends no request and closes when nothing changed', async () => {
    const wrapper = await mountDialog()
    vi.mocked(apiFetch).mockClear()

    await wrapper.find('form').trigger('submit')
    await flushPromises()

    expect(apiFetch).not.toHaveBeenCalled()
    expect(wrapper.emitted('update:open')?.slice(-1)[0]).toEqual([false])
  })
})
