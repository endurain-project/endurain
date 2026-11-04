import { beforeEach, describe, expect, it, vi } from 'vitest'

import { flushPromises, mount } from '@vue/test-utils'
import { QueryClient, VueQueryPlugin } from '@tanstack/vue-query'

import type { Component } from 'vue'
import type { VueWrapper } from '@vue/test-utils'
import type { Gear } from '@/features/gears/types'
import type { ProfileDetails } from '@/features/profile/types'
import type { ManagedUser } from '@/features/users/types'
import type { Schemas } from '@/types'

import i18n from '@/i18n'
import { HttpError, apiFetch } from '@/services/http'
import { applyServerFieldErrors } from '@/services/fieldErrors'
import GearFormDialog from '@/features/gears/components/GearFormDialog.vue'
import HealthWeightFormDialog from '@/features/health/components/HealthWeightFormDialog.vue'
import ProfileFormDialog from '@/features/profile/components/ProfileFormDialog.vue'
import UserFormDialog from '@/features/users/components/UserFormDialog.vue'

vi.mock('@/services/http', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/services/http')>()),
  apiFetch: vi.fn<typeof apiFetch>(),
}))

const t = i18n.global.t as (key: string) => string

type FieldError = Schemas['FieldError']

/** A 422 as the backend renders it: a problem document with an `errors` extension. */
function unprocessable(errors: FieldError[]): HttpError {
  return new HttpError(
    422,
    'Unprocessable Content',
    'The request could not be validated.',
    null,
    null,
    errors,
  )
}

describe('HttpError', () => {
  it('carries the field errors of a 422 problem document', async () => {
    const fetchMock = vi.fn<typeof fetch>().mockResolvedValue(
      new Response(
        JSON.stringify({
          detail: 'The request could not be validated.',
          errors: [{ field: 'body.name', message: 'Field required', type: 'missing' }],
        }),
        { status: 422 },
      ),
    )
    vi.stubGlobal('fetch', fetchMock)
    const { apiFetch: realFetch } =
      await vi.importActual<typeof import('@/services/http')>('@/services/http')

    await expect(realFetch('/x', { auth: false })).rejects.toMatchObject({
      status: 422,
      errors: [{ field: 'body.name', message: 'Field required', type: 'missing' }],
    })
    vi.unstubAllGlobals()
  })
})

describe('applyServerFieldErrors', () => {
  const keys = ['name', 'maxHeartRate', 'heightCm'] as const

  it('maps body fields to form keys and pydantic types to translated messages', () => {
    const setErrors = vi.fn<(errors: Partial<Record<string, string>>) => void>()
    const error = unprocessable([
      { field: 'body.name', message: 'Field required', type: 'missing' },
      { field: 'body.max_heart_rate', message: 'Input should be ≤ 250', type: 'less_than_equal' },
      { field: 'body.height', message: 'weird', type: 'something_new' },
    ])

    const mapped = applyServerFieldErrors(error, setErrors, t, keys, { height: 'heightCm' })

    expect(mapped).toBe(true)
    expect(setErrors).toHaveBeenCalledWith({
      name: t('app.fieldError.required'),
      maxHeartRate: t('app.fieldError.tooLarge'),
      heightCm: t('app.fieldError.invalid'),
    })
  })

  it('returns false and sets nothing for other errors and unknown fields', () => {
    const setErrors = vi.fn<(errors: Partial<Record<string, string>>) => void>()

    expect(applyServerFieldErrors(new HttpError(500, 'x'), setErrors, t, keys)).toBe(false)
    expect(applyServerFieldErrors(new Error('boom'), setErrors, t, keys)).toBe(false)
    expect(
      applyServerFieldErrors(
        unprocessable([{ field: 'query.page', message: 'm', type: 'missing' }]),
        setErrors,
        t,
        keys,
      ),
    ).toBe(false)
    expect(setErrors).not.toHaveBeenCalled()
  })
})

/** Passthrough stub so the reka-ui portal/focus-trap is skipped and the form renders inline. */
const passthrough = { template: '<div><slot /></div>' }

function mountDialog(component: Component, props: Record<string, unknown>) {
  return mount(component, {
    props: { open: false, ...props },
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
}

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

const profile: ProfileDetails = {
  ...user,
  timezone: 'UTC',
  hasLocalPassword: true,
  integrationsVersion: 1,
  stravaLinked: false,
  garminLinked: false,
  privacy: {} as ProfileDetails['privacy'],
}

const gear: Gear = {
  id: 2,
  userId: 1,
  gearType: 1,
  nickname: 'Road',
  brand: null,
  model: null,
  active: true,
  createdAt: '2026-01-01',
  initialKms: null,
  purchaseValue: null,
  stravaGearId: null,
  garminConnectGearId: null,
  version: 5,
}

const cases: [string, Component, Record<string, unknown>, FieldError, string][] = [
  [
    'UserFormDialog',
    UserFormDialog,
    { user },
    { field: 'body.max_heart_rate', message: 'm', type: 'less_than_equal' },
    t('app.fieldError.tooLarge'),
  ],
  [
    'HealthWeightFormDialog',
    HealthWeightFormDialog,
    { entry: null, weightUnits: 'metric' },
    { field: 'body.weight', message: 'm', type: 'greater_than_equal' },
    t('app.fieldError.tooSmall'),
  ],
  [
    'GearFormDialog',
    GearFormDialog,
    { gear, units: 'metric', currency: 'euro' },
    { field: 'body.nickname', message: 'm', type: 'string_too_long' },
    t('app.fieldError.tooLong'),
  ],
  [
    'ProfileFormDialog',
    ProfileFormDialog,
    { profile },
    { field: 'body.height', message: 'm', type: 'less_than_equal' },
    t('app.fieldError.tooLarge'),
  ],
]

describe.each(cases)('%s 422 handling', (_name, component, props, fieldError, message) => {
  let wrapper: VueWrapper

  beforeEach(async () => {
    vi.clearAllMocks()
    vi.mocked(apiFetch).mockRejectedValue(unprocessable([fieldError]))
    wrapper = mountDialog(component, props)
    await wrapper.setProps({ open: true })
  })

  it('shows the field error and keeps the dialog open without a toast', async () => {
    // An unchanged edit is not sent, so change a field first.
    if (component === HealthWeightFormDialog) {
      await wrapper.findAll('input')[1]!.setValue('77')
    } else {
      await wrapper.find('input').setValue('Changed')
    }
    await wrapper.find('form').trigger('submit')
    await flushPromises()

    expect(apiFetch).toHaveBeenCalled()
    expect(wrapper.text()).toContain(message)
    expect(wrapper.emitted('error')).toBeUndefined()
    expect(wrapper.emitted('update:open')).toBeUndefined()
  })

  it('falls back to the toast when no field can be mapped', async () => {
    vi.mocked(apiFetch).mockRejectedValue(
      unprocessable([{ field: 'body.unknown_thing', message: 'm', type: 'missing' }]),
    )
    // An unchanged edit is not sent, so change a field first.
    if (component === HealthWeightFormDialog) {
      await wrapper.findAll('input')[1]!.setValue('77')
    } else {
      await wrapper.find('input').setValue('Changed')
    }
    await wrapper.find('form').trigger('submit')
    await flushPromises()

    expect(wrapper.emitted('error')).toHaveLength(1)
  })
})
