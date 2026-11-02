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
  integrationsVersion: 1,
  stravaLinked: false,
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
  await wrapper.find('form').trigger('submit')
  await flushPromises()
  const [, init] = vi.mocked(apiFetch).mock.calls.slice(-1)[0]!
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

    expect(await saveBody(wrapper)).toMatchObject({ units: 'imperial', height: 172 })
  })

  it('converts the feet and inches the user edits', async () => {
    vi.mocked(apiFetch).mockResolvedValue({ ...profile })
    const wrapper = await mountDialog({ ...profile, units: 'imperial' })

    await wrapper.find('input[name="heightInches"]').setValue('9')

    expect(await saveBody(wrapper)).toMatchObject({ height: 175 })
  })
})
