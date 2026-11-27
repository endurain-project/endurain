import { beforeEach, describe, expect, it, vi } from 'vitest'

import { flushPromises, mount } from '@vue/test-utils'
import { QueryClient, VueQueryPlugin } from '@tanstack/vue-query'
import { defineComponent, h, ref } from 'vue'

import type { ActivityType } from '@/features/activities/types'

import { apiFetch } from '@/services/http'
import i18n from '@/i18n'
import ActivityDetailView from '@/features/activities/views/ActivityDetailView.vue'
import ActivityLegSwitcher from '@/features/activities/components/ActivityLegSwitcher.vue'
import ActivityLegsTable from '@/features/activities/components/ActivityLegsTable.vue'
import ActivityActionsMenu from '@/features/activities/components/ActivityActionsMenu.vue'
import ActivityListItem from '@/features/activities/components/ActivityListItem.vue'
import HomeActivityCard from '@/features/home/components/HomeActivityCard.vue'
import { useActivityLegsTrack } from '@/features/activities/composables/useActivityDetail'
import { ACTIVITY_METRIC_COLUMNS } from '@/features/activities/utils/activityListColumns'
import { labelLegs } from '@/features/activities/utils/legs'
import { buildActivityMetrics } from '@/features/activities/utils/metrics'
import { presentActivityType } from '@/features/activities/utils/activityType'
import { activityUuid, makeActivity, makeActivitySummary, userUuid } from './fixtures/activity'

const { route, currentUser, auth } = vi.hoisted(() => ({
  route: { params: {} as Record<string, unknown> },
  auth: { isAuthenticated: true },
  currentUser: { value: null as { id: string; name: string; username: string } | null },
}))

vi.mock('vue-router', () => ({
  useRoute: () => route,
  useRouter: () => ({ push: vi.fn<(to: unknown) => Promise<void>>() }),
  RouterLink: {
    props: ['to'],
    template: '<a :data-id="to.params && to.params.id"><slot /></a>',
  },
}))
vi.mock('@/services/http', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/services/http')>()),
  apiFetch: vi.fn<typeof apiFetch>(),
}))
vi.mock('pinia', async (importOriginal) => ({
  ...(await importOriginal<typeof import('pinia')>()),
  storeToRefs: () => ({ isAuthenticated: ref(true) }),
}))
vi.mock('@/features/auth/stores/auth', () => ({ useAuthStore: () => auth }))
vi.mock('@/features/auth/composables/useCurrentUser', () => ({
  useCurrentUser: () => ({ data: ref(currentUser.value) }),
}))

const OWNER = { id: userUuid(7), name: 'Jane', username: 'jane', avatarUrl: null, units: 'metric' }
const PARENT_ID = activityUuid(1)
const SWIM_ID = activityUuid(2)
const T1_ID = activityUuid(3)
const BIKE_ID = activityUuid(4)
const T2_ID = activityUuid(5)
const RUN_ID = activityUuid(6)

/** The legs of the triathlon, in leg order: swim, transition, bike, transition, run. */
const LEG_TYPES: [string, ActivityType][] = [
  [SWIM_ID, 'open_water_swimming'],
  [T1_ID, 'transition'],
  [BIKE_ID, 'ride'],
  [T2_ID, 'transition'],
  [RUN_ID, 'run'],
]

const page = (items: unknown[], next: number | null = null) => ({
  items,
  total: items.length,
  page: 1,
  num_records: 200,
  next,
})

/** A leg's list row as the API returns it. */
function legDto(id: string, type: ActivityType, overrides: Record<string, unknown> = {}) {
  return {
    id,
    user_id: OWNER.id,
    version: 1,
    name: `Leg ${id.slice(-1)}`,
    activity_type: type,
    parent_activity_id: PARENT_ID,
    distance: 5000,
    is_hidden: false,
    visibility: 'public',
    total_timer_time: 1200,
    average_hr: 140,
    ...overrides,
  }
}

const LEG_DTOS = LEG_TYPES.map(([id, type]) =>
  legDto(id, type, id === T1_ID || id === T2_ID ? { distance: 0, average_hr: null } : {}),
)

/** The multisport activity: the legs' totals, and no pace, speed or cadence. */
const parentDto = {
  id: PARENT_ID,
  user_id: OWNER.id,
  version: 1,
  name: 'Sunday triathlon',
  activity_type: 'multisport',
  parent_activity_id: null,
  distance: 25000,
  is_hidden: false,
  visibility: 'public',
  total_timer_time: 6000,
  total_elapsed_time: 6100,
  average_hr: 150,
  max_hr: 180,
  calories: 1800,
  pace: null,
  average_speed: null,
}

/** One GPS track per leg, so the leg order shows in the joined route. */
const TRACKS: Record<string, { lat: number; lon: number }[]> = {
  [SWIM_ID]: [
    { lat: 1, lon: 1 },
    { lat: 1, lon: 2 },
  ],
  [BIKE_ID]: [
    { lat: 3, lon: 1 },
    { lat: 3, lon: 2 },
  ],
  [RUN_ID]: [{ lat: 5, lon: 1 }],
}

/** The samples answer for a track: its positions on the lat/lon channels, null without a track. */
function samples(track: { lat: number; lon: number }[]) {
  const channel = (values: number[] | null) => (track.length > 0 ? values : null)
  return {
    offsets_ms: track.map((_, index) => index * 1000),
    latitude: channel(track.map((point) => point.lat)),
    longitude: channel(track.map((point) => point.lon)),
    elevation: null,
    heart_rate: null,
    power: null,
    cadence: null,
    speed: null,
    pace: null,
    temperature: null,
    heart_rate_zones: null,
  }
}

/** Answers the activity routes the detail page reads. */
function serve(overrides: Record<string, unknown> = {}) {
  vi.mocked(apiFetch).mockImplementation((path: string) => {
    const [url = ''] = path.split('?')
    const id = url.split('/').find((part) => part.length === 36) ?? ''
    const leg = LEG_DTOS.find((dto) => dto.id === id)
    if (url.endsWith('/detail')) {
      const activity = id === PARENT_ID ? { ...parentDto, ...overrides } : leg
      const legs = id === PARENT_ID ? LEG_DTOS : []
      return Promise.resolve({
        activity,
        laps: page([]),
        sets: page([]),
        workout_steps: page([]),
        legs: page(legs),
        owner: null,
      })
    }
    if (url.endsWith('/legs')) {
      return Promise.resolve(page(id === PARENT_ID ? LEG_DTOS : []))
    }
    if (url.endsWith('/streams')) {
      return Promise.resolve(samples(TRACKS[id] ?? []))
    }
    return Promise.resolve([])
  }) as never
}

const MapStub = {
  props: ['points'],
  template: '<div data-testid="map" :data-points="JSON.stringify(points)" />',
}

async function mountView(id: string) {
  route.params = { id }
  const wrapper = mount(ActivityDetailView, {
    global: {
      plugins: [i18n, [VueQueryPlugin, { queryClient: new QueryClient() }]],
      stubs: { ActivityMap: MapStub },
    },
  })
  await flushPromises()
  return wrapper
}

function requestedPaths(): string[] {
  return vi.mocked(apiFetch).mock.calls.map(([path]) => String(path).split('?')[0] ?? '')
}

function t(key: string, values?: Record<string, unknown>): string {
  return i18n.global.t(key, values ?? {})
}

describe('labelLegs', () => {
  const legs = LEG_TYPES.map(([id, type]) => makeActivitySummary({ id, activityType: type }))
  const keyOf = (type: ActivityType) => presentActivityType(type).labelKey

  it('numbers the transitions in leg order when there are several', () => {
    expect(labelLegs(legs, keyOf).map((entry) => entry.number)).toEqual([null, 1, null, 2, null])
  })

  it('leaves a single transition unnumbered', () => {
    const [swim, transition, bike] = legs
    const labels = labelLegs([swim!, transition!, bike!], keyOf)

    expect(labels.map((entry) => entry.number)).toEqual([null, null, null])
    expect(labels[1]?.labelKey).toBe('activities.types.transition')
  })
})

describe('ActivityLegSwitcher', () => {
  function mountSwitcher(activeId: string) {
    return mount(ActivityLegSwitcher, {
      props: {
        parentId: PARENT_ID,
        activeId,
        legs: LEG_TYPES.map(([id, type]) => makeActivitySummary({ id, activityType: type })),
      },
      global: {
        plugins: [i18n],
        stubs: {
          RouterLink: { props: ['to'], template: '<a :data-id="to.params.id"><slot /></a>' },
        },
      },
    })
  }

  it('is a labelled navigation of links, not a tab list', () => {
    const wrapper = mountSwitcher(PARENT_ID)

    expect(wrapper.find('nav').attributes('aria-label')).toBe(t('activities.multisport.switcher'))
    expect(wrapper.findAll('[role="tab"]')).toHaveLength(0)
  })

  it('offers Overview and one tab per leg, labelled by sport with numbered transitions', () => {
    const tabs = mountSwitcher(PARENT_ID).findAll('nav a')

    expect(tabs.map((tab) => tab.text())).toEqual([
      t('activities.multisport.overview'),
      t('activities.types.openWaterSwimming'),
      t('activities.multisport.numberedLeg', {
        label: t('activities.types.transition'),
        number: 1,
      }),
      t('activities.types.ride'),
      t('activities.multisport.numberedLeg', {
        label: t('activities.types.transition'),
        number: 2,
      }),
      t('activities.types.run'),
    ])
    expect(tabs[1]?.text()).not.toBe(tabs[2]?.text())
    expect(tabs[2]?.text()).toBe('Transition 1')
    expect(tabs[4]?.text()).toBe('Transition 2')
  })

  it('links each tab to its activity: Overview to the parent, a leg tab to the leg', () => {
    const tabs = mountSwitcher(PARENT_ID).findAll('nav a')

    expect(tabs.map((tab) => tab.attributes('data-id'))).toEqual([
      PARENT_ID,
      SWIM_ID,
      T1_ID,
      BIKE_ID,
      T2_ID,
      RUN_ID,
    ])
  })

  it('marks Overview active on the parent and a leg tab active on that leg', () => {
    const onParent = mountSwitcher(PARENT_ID).findAll('nav a')
    const onBike = mountSwitcher(BIKE_ID).findAll('nav a')

    expect(onParent.map((tab) => tab.attributes('aria-current'))).toEqual([
      'page',
      undefined,
      undefined,
      undefined,
      undefined,
      undefined,
    ])
    expect(onBike.map((tab) => tab.attributes('aria-current'))).toEqual([
      undefined,
      undefined,
      undefined,
      'page',
      undefined,
      undefined,
    ])
  })
})

describe('ActivityLegsTable', () => {
  function mountTable(legs = LEG_TYPES, currentUserId: string | null = OWNER.id, overrides = {}) {
    return mount(ActivityLegsTable, {
      props: {
        legs: legs.map(([id, type]) =>
          makeActivitySummary({
            id,
            activityType: type,
            name: `Leg ${id.slice(-1)}`,
            userId: OWNER.id,
            distance: type === 'transition' ? 0 : 5000,
            totalTimerTime: 1200,
            pace: 0.3,
            averageSpeed: 8,
            averageHr: 140,
            ...overrides,
          }),
        ),
        units: 'metric',
        currentUserId,
      },
      global: {
        plugins: [i18n],
        stubs: {
          RouterLink: { props: ['to'], template: '<a :data-id="to.params.id"><slot /></a>' },
        },
      },
    })
  }

  it('lists a row per leg with its name linked to the leg, time, distance, tempo and heart rate', () => {
    const rows = mountTable().findAll('tbody tr')

    expect(rows).toHaveLength(5)
    expect(rows.map((row) => row.find('a').attributes('data-id'))).toEqual(
      LEG_TYPES.map(([id]) => id),
    )
    const swim = rows[0]!.findAll('td').map((cell) => cell.text())
    expect(swim[0]).toBe('Leg 2')
    expect(swim[1]).toBe('20:00')
    expect(swim[2]).toBe('5,000 m')
    expect(swim[3]).toContain('/100')
    expect(swim[4]).toContain('140')
  })

  it('shows speed for a cycling leg and pace for a running leg, as the sport shows them elsewhere', () => {
    const rows = mountTable().findAll('tbody tr')

    expect(rows[2]!.findAll('td')[3]!.text()).toBe('28.80 km/h')
    expect(rows[4]!.findAll('td')[3]!.text()).toContain('/km')
  })

  it('shows a dash for what a transition has no reading of', () => {
    const cells = mountTable([[T1_ID, 'transition']], OWNER.id, {
      averageHr: null,
      pace: null,
      averageSpeed: null,
    })
      .findAll('td')
      .map((cell) => cell.text())

    expect(cells.slice(2)).toEqual(['--', '--', '--'])
  })

  it('keeps hidden fields hidden from a viewer who is not the owner', () => {
    const hidden = { privacy: { hideHr: true, hidePace: true, hideSpeed: true } }
    const cells = mountTable([[RUN_ID, 'run']], userUuid(9), hidden)
      .findAll('td')
      .map((cell) => cell.text())

    expect(cells[3]).toBe('--')
    expect(cells[4]).toBe('--')
    expect(cells[2]).toBe('5.00 km')
  })
})

describe('useActivityLegsTrack', () => {
  async function trackOf(ids: string[], enabled = true) {
    let points: ReturnType<typeof useActivityLegsTrack> | undefined
    const wrapper = mount(
      defineComponent({
        setup() {
          points = useActivityLegsTrack(ids, enabled)
          return () => h('div')
        },
      }),
      { global: { plugins: [[VueQueryPlugin, { queryClient: new QueryClient() }]] } },
    )
    await flushPromises()
    wrapper.unmount()
    return points?.value
  }

  beforeEach(() => {
    vi.mocked(apiFetch).mockReset()
    serve()
  })

  it('joins the legs tracks in leg order, skipping a leg without a track', async () => {
    const points = await trackOf(LEG_TYPES.map(([id]) => id))

    expect(points).toEqual([
      { lat: 1, lng: 1 },
      { lat: 1, lng: 2 },
      { lat: 3, lng: 1 },
      { lat: 3, lng: 2 },
      { lat: 5, lng: 1 },
    ])
  })

  it('reads nothing while disabled', async () => {
    expect(await trackOf([SWIM_ID], false)).toEqual([])
    expect(apiFetch).not.toHaveBeenCalled()
  })
})

describe('ActivityDetailView on a multisport activity', () => {
  beforeEach(() => {
    vi.mocked(apiFetch).mockReset()
    currentUser.value = OWNER
    serve()
  })

  it('shows the parent totals in the header with the multisport badge and no pace or speed pill', async () => {
    const wrapper = await mountView(PARENT_ID)
    const text = wrapper.text()

    expect(text).toContain('Sunday triathlon')
    expect(text).toContain(t('activities.types.multisport'))
    expect(text).toContain(t('activities.metrics.distance'))
    expect(text).toContain('25.00')
    expect(text).toContain('1:40:00')
    expect(text).toContain('1,800')
    expect(text).not.toContain(t('activities.metrics.avgPace'))
    expect(text).not.toContain(t('activities.metrics.avgSpeed'))
    expect(text).not.toContain('NaN')
  })

  it('puts the leg switcher under the header with Overview active', async () => {
    const wrapper = await mountView(PARENT_ID)
    const tabs = wrapper.findAll('nav a')

    expect(tabs.map((tab) => tab.text())).toEqual([
      t('activities.multisport.overview'),
      t('activities.types.openWaterSwimming'),
      'Transition 1',
      t('activities.types.ride'),
      'Transition 2',
      t('activities.types.run'),
    ])
    expect(tabs[0]?.attributes('aria-current')).toBe('page')
    expect(tabs.slice(1).map((tab) => tab.attributes('data-id'))).toEqual(
      LEG_TYPES.map(([id]) => id),
    )
  })

  it('lists the legs in a table whose rows link to the legs', async () => {
    const wrapper = await mountView(PARENT_ID)
    const rows = wrapper.findAll('tbody tr')

    expect(wrapper.text()).toContain(t('activities.multisport.legs'))
    expect(rows).toHaveLength(5)
    expect(rows.map((row) => row.find('a').attributes('data-id'))).toEqual(
      LEG_TYPES.map(([id]) => id),
    )
  })

  it('draws one route made of the legs tracks in leg order', async () => {
    const wrapper = await mountView(PARENT_ID)

    const map = wrapper.find('[data-testid="map"]')
    expect(JSON.parse(map.attributes('data-points') ?? '[]')).toEqual([
      { lat: 1, lng: 1 },
      { lat: 1, lng: 2 },
      { lat: 3, lng: 1 },
      { lat: 3, lng: 2 },
      { lat: 5, lng: 1 },
    ])
  })

  it('leaves out the map of a viewer the privacy hides it from, without reading the legs streams', async () => {
    currentUser.value = null
    serve({ hide_map: true })

    const wrapper = await mountView(PARENT_ID)

    expect(wrapper.find('[data-testid="map"]').exists()).toBe(false)
    expect(requestedPaths().some((path) => path.endsWith('/streams'))).toBe(false)
  })

  it('hides the sections the parent has no data for and reads none of them', async () => {
    const wrapper = await mountView(PARENT_ID)

    expect(wrapper.text()).not.toContain(t('activities.laps.title'))
    expect(wrapper.text()).not.toContain(t('activities.workout.title'))
    expect(wrapper.text()).not.toContain(t('activities.gear.title'))
    expect(requestedPaths()).not.toContain(`/activities/${PARENT_ID}/streams`)
    expect(requestedPaths()).not.toContain(`/activities/${PARENT_ID}/laps`)
  })

  it('reads the multisport activity and its legs from the public routes for an anonymous viewer', async () => {
    auth.isAuthenticated = false
    currentUser.value = null
    try {
      const wrapper = await mountView(PARENT_ID)

      expect(wrapper.findAll('tbody tr')).toHaveLength(5)
      expect(wrapper.findAll('nav a')).toHaveLength(6)
      expect(
        JSON.parse(wrapper.get('[data-testid="map"]').attributes('data-points') ?? '[]'),
      ).toHaveLength(5)
      const paths = requestedPaths()
      expect(paths).toContain(`/public/activities/${PARENT_ID}/detail`)
      expect(paths).toContain(`/public/activities/${BIKE_ID}/streams`)
      expect(paths.filter((path) => !path.startsWith('/public/'))).toEqual([])
    } finally {
      auth.isAuthenticated = true
    }
  })

  it('reads the legs from the public legs route when the detail held only the first page', async () => {
    auth.isAuthenticated = false
    currentUser.value = null
    serve()
    const detail = vi.mocked(apiFetch).getMockImplementation()!
    vi.mocked(apiFetch).mockImplementation((path: string, options?: unknown) =>
      String(path).endsWith('/detail')
        ? Promise.resolve({
            activity: parentDto,
            laps: page([]),
            sets: page([]),
            workout_steps: page([]),
            legs: page(LEG_DTOS.slice(0, 1), 2),
            owner: null,
          })
        : detail(path, options as never),
    ) as never
    try {
      const wrapper = await mountView(PARENT_ID)

      expect(requestedPaths()).toContain(`/public/activities/${PARENT_ID}/legs`)
      expect(wrapper.findAll('tbody tr')).toHaveLength(5)
    } finally {
      auth.isAuthenticated = true
    }
  })
})

describe('ActivityDetailView on a leg', () => {
  beforeEach(() => {
    vi.mocked(apiFetch).mockReset()
    currentUser.value = OWNER
    serve()
  })

  it('keeps the leg page and adds the switcher with this leg active', async () => {
    const wrapper = await mountView(BIKE_ID)
    const tabs = wrapper.findAll('nav a')

    expect(wrapper.find('h1').text()).toBe('Leg 4')
    expect(tabs).toHaveLength(6)
    expect(tabs.map((tab) => tab.attributes('aria-current'))).toEqual([
      undefined,
      undefined,
      undefined,
      'page',
      undefined,
      undefined,
    ])
    expect(requestedPaths()).toContain(`/activities/${BIKE_ID}/streams`)
  })

  it('links back to the multisport activity', async () => {
    const wrapper = await mountView(BIKE_ID)
    const back = wrapper
      .findAll('a')
      .find(
        (link) => link.text() === t('activities.multisport.partOf', { name: 'Sunday triathlon' }),
      )

    expect(back?.attributes('data-id')).toBe(PARENT_ID)
  })

  it('does not mention legs on a multisport activity that has none', async () => {
    vi.mocked(apiFetch).mockReset()
    vi.mocked(apiFetch).mockImplementation((path: string) =>
      Promise.resolve(
        String(path).endsWith('/detail')
          ? {
              activity: parentDto,
              laps: page([]),
              sets: page([]),
              workout_steps: page([]),
              legs: page([]),
              owner: null,
            }
          : page([]),
      ),
    ) as never

    const wrapper = await mountView(PARENT_ID)

    expect(wrapper.findAll('nav a')).toHaveLength(0)
    expect(wrapper.text()).not.toContain(t('activities.multisport.legs'))
  })

  it('shows no legs table and no multisport link on an ordinary activity', async () => {
    vi.mocked(apiFetch).mockReset()
    vi.mocked(apiFetch).mockImplementation((path: string) =>
      Promise.resolve(
        String(path).endsWith('/detail')
          ? {
              activity: { ...parentDto, activity_type: 'run' },
              laps: page([]),
              sets: page([]),
              workout_steps: page([]),
              legs: page([]),
              owner: null,
            }
          : page([]),
      ),
    ) as never

    const wrapper = await mountView(PARENT_ID)

    expect(wrapper.findAll('nav a')).toHaveLength(0)
    expect(wrapper.text()).not.toContain(t('activities.multisport.legs'))
  })
})

describe('ActivityActionsMenu on multisport activities', () => {
  const passthrough = { template: '<div><slot /></div>' }
  const confirmStub = {
    props: ['description'],
    template: '<p data-testid="confirm">{{ description }}</p>',
  }

  function mountMenu(activity: ReturnType<typeof makeActivity>) {
    return mount(ActivityActionsMenu, {
      props: { activity },
      global: {
        plugins: [i18n, [VueQueryPlugin, { queryClient: new QueryClient() }]],
        stubs: {
          DropdownMenu: passthrough,
          DropdownMenuContent: passthrough,
          DropdownMenuTrigger: passthrough,
          DropdownMenuItem: passthrough,
          DropdownMenuSeparator: passthrough,
          ActivityEditDialog: true,
          ConfirmDialog: confirmStub,
        },
      },
    })
  }

  it('says the legs are deleted too when deleting a multisport activity', () => {
    const wrapper = mountMenu(
      makeActivity({ name: 'Sunday triathlon', activityType: 'multisport' }),
    )

    expect(wrapper.get('[data-testid="confirm"]').text()).toBe(
      t('activities.actions.deleteMultisportBody', { name: 'Sunday triathlon' }),
    )
    expect(t('activities.actions.deleteMultisportBody', { name: 'x' })).toContain('legs')
  })

  it('keeps the plain confirmation for an ordinary activity', () => {
    const wrapper = mountMenu(makeActivity({ name: 'Morning run' }))

    expect(wrapper.get('[data-testid="confirm"]').text()).toBe(
      t('activities.actions.deleteBody', { name: 'Morning run' }),
    )
  })

  it('does not offer delete for a leg', () => {
    const wrapper = mountMenu(makeActivity({ parentActivityId: PARENT_ID }))

    expect(wrapper.text()).not.toContain(t('activities.actions.delete'))
    expect(wrapper.text()).toContain(t('activities.actions.edit'))
  })

  it('offers delete for an ordinary activity', () => {
    const wrapper = mountMenu(makeActivity())

    expect(wrapper.text()).toContain(t('activities.actions.delete'))
  })
})

describe('a multisport activity with no pace or speed', () => {
  const multisport = makeActivitySummary({
    id: PARENT_ID,
    activityType: 'multisport',
    name: 'Sunday triathlon',
    pace: null,
    averageSpeed: null,
    maxSpeed: null,
    averageCadence: null,
    distance: 25000,
    totalTimerTime: 6000,
  })
  const everything = {
    pace: true,
    speed: true,
    hr: true,
    power: true,
    cadence: true,
    elevation: true,
  }

  it('builds metric tiles without a pace or speed tile', () => {
    const keys = buildActivityMetrics(multisport, 'metric', everything).map((tile) => tile.key)

    expect(keys).toContain('distance')
    expect(keys).toContain('time')
    expect(keys).not.toContain('pace')
    expect(keys).not.toContain('avgSpeed')
  })

  it('shows the list row with the multisport label, the totals and empty pace and speed', () => {
    const wrapper = mount(ActivityListItem, {
      props: { activity: multisport, units: 'metric', columns: ACTIVITY_METRIC_COLUMNS },
      global: {
        plugins: [i18n],
        stubs: { RouterLink: { props: ['to'], template: '<a><slot /></a>' } },
      },
    })
    const text = wrapper.text()

    expect(text).toContain('Sunday triathlon')
    expect(text).toContain('25.00')
    expect(text).toContain('1:40:00')
    expect(text).not.toContain('NaN')
    expect(text).not.toMatch(/\b0(\.0+)?\s*(km\/h|\/km)/)
    expect(wrapper.findAll('p').filter((p) => p.text() === '—')).toHaveLength(1)
  })

  it('shows the feed card with the multisport badge and the totals but no pace or speed pill', async () => {
    const wrapper = mount(HomeActivityCard, {
      props: { activity: multisport, units: 'metric', currentUserId: OWNER.id },
      global: {
        plugins: [i18n, [VueQueryPlugin, { queryClient: new QueryClient() }]],
        stubs: {
          RouterLink: { props: ['to'], template: '<a><slot /></a>' },
          ActivityGallery: true,
          ActivityActionsMenu: true,
        },
      },
    })
    await flushPromises()
    const text = wrapper.text()

    expect(text).toContain(t('activities.types.multisport'))
    expect(text).toContain('25.00')
    expect(text).not.toContain(t('activities.metrics.avgPace'))
    expect(text).not.toContain(t('activities.metrics.avgSpeed'))
    expect(text).not.toContain('NaN')
  })
})
