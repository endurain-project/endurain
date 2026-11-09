import { mount } from '@vue/test-utils'
import { describe, expect, it, vi } from 'vitest'
import { ref } from 'vue'

import { QueryClient, VueQueryPlugin } from '@tanstack/vue-query'

import type { ManagedUser } from '@/features/users/types'

import { apiFetch, HttpError } from '@/services/http'
import i18n from '@/i18n'
import UserFormDialog from '@/features/users/components/UserFormDialog.vue'

vi.mock('@/services/http', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/services/http')>()),
  apiFetch: vi.fn<typeof apiFetch>(),
}))

vi.mock('@/features/security/composables/useAdminStepUp', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/features/security/composables/useAdminStepUp')>()),
  useAdminStepUp: () => ({ requirePassword: ref(true), requireMfa: ref(false) }),
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

const passthrough = { template: '<div><slot /></div>' }
const routerLink = { props: ['to'], template: '<a><slot /></a>' }

/** Saves a name-only edit (no step-up) that the server refuses with the given problem. */
async function saveRefusedWith(error: HttpError) {
  vi.mocked(apiFetch).mockImplementation((_path, init) =>
    init?.method === 'PATCH' ? Promise.reject(error) : Promise.resolve({ ...user }),
  )
  const wrapper = mount(UserFormDialog, {
    props: { open: false, user, isSelf: false },
    global: {
      plugins: [i18n, [VueQueryPlugin, { queryClient: new QueryClient() }]],
      stubs: {
        Dialog: passthrough,
        DialogContent: passthrough,
        DialogHeader: passthrough,
        DialogTitle: passthrough,
        DialogDescription: passthrough,
        DialogFooter: passthrough,
        RouterLink: routerLink,
      },
    },
  })
  await wrapper.setProps({ open: true })
  await wrapper.find('input[name="name"]').setValue('Renamed')
  await wrapper.find('form').trigger('submit')
  await vi.waitFor(() => expect(wrapper.emitted('error')).toBeDefined())
  return wrapper
}

describe('UserFormDialog refusals', () => {
  it('names the last administrator when the server refuses to demote or deactivate them', async () => {
    const wrapper = await saveRefusedWith(
      new HttpError(409, 'Conflict', null, 'urn:endurain:error:last-administrator'),
    )

    expect(wrapper.emitted('error')?.[0]).toEqual([
      i18n.global.t('settings.users.form.lastAdministrator'),
    ])
  })

  it('reports any other conflict as a username or email already in use', async () => {
    const wrapper = await saveRefusedWith(
      new HttpError(409, 'Conflict', null, 'urn:endurain:error:conflict'),
    )

    expect(wrapper.emitted('error')?.[0]).toEqual([i18n.global.t('settings.users.form.conflict')])
  })
})
