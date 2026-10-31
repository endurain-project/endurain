import { afterEach, describe, expect, it, vi } from 'vitest'
import { ref } from 'vue'
import { mount } from '@vue/test-utils'

import type { ProfileDetails } from '@/features/profile/types'

import i18n from '@/i18n'
import ProfileInfoCard from '@/features/profile/components/ProfileInfoCard.vue'

vi.mock('@/composables/useToasts', () => ({
  useToasts: () => ({
    success: vi.fn<(message: string) => void>(),
    error: vi.fn<(message: string) => void>(),
  }),
}))
vi.mock('@/features/profile/composables/useProfile', () => ({
  useUpdateProfileMutation: () => ({
    mutate: vi.fn<(...args: unknown[]) => void>(),
    isPending: ref(false),
  }),
  useUploadProfilePhotoMutation: () => ({
    mutate: vi.fn<(...args: unknown[]) => void>(),
    isPending: ref(false),
  }),
  useDeleteProfilePhotoMutation: () => ({
    mutate: vi.fn<(...args: unknown[]) => void>(),
    isPending: ref(false),
  }),
}))

const mounted: Array<{ unmount: () => void }> = []

/** Builds a full profile for the card, overridable per case. */
function makeProfile(overrides: Partial<ProfileDetails> = {}): ProfileDetails {
  return {
    id: 1,
    version: 1,
    name: 'Ada Lovelace',
    username: 'ada',
    email: 'ada@example.com',
    pendingEmail: null,
    pendingEmailExpiresAt: null,
    city: 'London',
    birthdate: '1990-01-01',
    gender: 'female',
    units: 'metric',
    weightUnits: null,
    currency: 'euro',
    height: 170,
    maxHeartRate: null,
    preferredLanguage: 'en',
    firstDayOfWeek: 'monday',
    timezone: null,
    accessType: 'regular',
    hasLocalPassword: true,
    integrationsVersion: 1,
    stravaLinked: false,
    garminLinked: false,
    photoPath: null,
    avatarUrl: null,
    privacy: {
      version: 1,
      defaultActivityVisibility: 'followers',
      hideStartTime: false,
      hideLocation: false,
      hideMap: false,
      hideHr: false,
      hidePower: false,
      hideCadence: false,
      hideElevation: false,
      hideSpeed: false,
      hidePace: false,
      hideLaps: false,
      hideWorkoutSetsSteps: false,
      hideGear: false,
    },
    ...overrides,
  }
}

/** Mounts the card with the edit and photo-confirm dialogs stubbed out. */
function mountCard(profile: ProfileDetails) {
  const wrapper = mount(ProfileInfoCard, {
    props: { profile },
    global: { plugins: [i18n], stubs: { ProfileFormDialog: true, ConfirmDialog: true } },
  })
  mounted.push(wrapper)
  return wrapper
}

/** Reads the value rendered for a field label, or `''` when the row is absent. */
function valueFor(wrapper: ReturnType<typeof mountCard>, label: string): string {
  const row = wrapper.findAll('dl > div').find((node) => node.find('dt').text() === label)
  return row ? row.find('dd').text() : ''
}

describe('ProfileInfoCard', () => {
  afterEach(() => {
    mounted.splice(0).forEach((wrapper) => wrapper.unmount())
  })

  it('shows the weight units override next to the measurement system', () => {
    const wrapper = mountCard(makeProfile({ units: 'metric', weightUnits: 'imperial' }))
    expect(valueFor(wrapper, 'Units')).toBe('Metric')
    expect(valueFor(wrapper, 'Weight units')).toBe('Pounds (lbs)')
  })

  it('shows the weight units the units setting implies when no override is set', () => {
    const metric = mountCard(makeProfile({ units: 'metric', weightUnits: null }))
    expect(valueFor(metric, 'Weight units')).toBe('Kilograms (kg)')

    const imperial = mountCard(makeProfile({ units: 'imperial', weightUnits: null }))
    expect(valueFor(imperial, 'Weight units')).toBe('Pounds (lbs)')
  })
})
