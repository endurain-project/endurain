import { defineComponent, h, ref } from 'vue'
import { flushPromises, mount } from '@vue/test-utils'
import { QueryClient, VueQueryPlugin } from '@tanstack/vue-query'
import { afterEach, describe, expect, it, vi } from 'vitest'

import type { FollowList } from '@/features/followers/types'
import type { PublicUser } from '@/features/users/types'

import { queryKeys } from '@/services/queryKeys'
import { fetchFollowers, fetchFollowing } from '@/features/followers/services/followers'
import { fetchPublicUser } from '@/features/users/services/publicUsers'
import { useFollowersQuery, useFollowingQuery } from '@/features/followers/composables/useFollowers'
import { usePublicUserQuery } from '@/features/users/composables/usePublicUser'

vi.mock('pinia', async (importOriginal) => ({
  ...(await importOriginal<typeof import('pinia')>()),
  storeToRefs: () => ({ isAuthenticated: ref(true) }),
}))

vi.mock('@/features/auth/stores/auth', () => ({ useAuthStore: () => ({}) }))
vi.mock('@/features/auth/composables/useCurrentUser', () => ({
  useCurrentUser: () => ({ data: ref({ id: 1 }) }),
}))

vi.mock('@/features/followers/services/followers', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/features/followers/services/followers')>()),
  fetchFollowers: vi.fn<(userId: number) => Promise<FollowList>>(),
  fetchFollowing: vi.fn<(userId: number) => Promise<FollowList>>(),
}))

vi.mock('@/features/users/services/publicUsers', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/features/users/services/publicUsers')>()),
  fetchPublicUser: vi.fn<(userId: number) => Promise<PublicUser | null>>(),
}))

const ada: PublicUser = { id: 3, name: 'Ada', username: 'ada', city: null, avatarUrl: null }

const followList: FollowList = {
  edges: [
    { userId: 3, isAccepted: true },
    { userId: 4, isAccepted: false },
  ],
  profiles: new Map<number, PublicUser | null>([
    [3, ada],
    [4, null],
  ]),
}

let wrapper: ReturnType<typeof mount> | undefined

afterEach(() => {
  wrapper?.unmount()
  wrapper = undefined
  vi.clearAllMocks()
})

/** Mounts a component that runs `setup` against the given client. */
function mountWith(queryClient: QueryClient, setup: () => void): void {
  wrapper = mount(
    defineComponent({
      setup() {
        setup()
        return () => h('div')
      },
    }),
    { global: { plugins: [[VueQueryPlugin, { queryClient }]] } },
  )
}

describe.each([
  ['followers', useFollowersQuery, fetchFollowers],
  ['following', useFollowingQuery, fetchFollowing],
])('the %s list', (_name, useListQuery, fetchList) => {
  it('exposes just the edges, not the profiles that rode along', async () => {
    vi.mocked(fetchList).mockResolvedValue(followList)
    let list: ReturnType<typeof useFollowersQuery> | undefined
    mountWith(new QueryClient(), () => {
      list = useListQuery(9)
    })
    await flushPromises()

    expect(list?.data.value).toEqual(followList.edges)
  })

  it('waits until enabled before fetching the list', async () => {
    const enabled = ref(false)
    vi.mocked(fetchList).mockResolvedValue(followList)
    mountWith(new QueryClient(), () => {
      useListQuery(9, enabled)
    })
    await flushPromises()

    expect(fetchList).not.toHaveBeenCalled()

    enabled.value = true
    await flushPromises()

    expect(fetchList).toHaveBeenCalledOnce()
  })

  it('keeps the cached list fresh for one minute', async () => {
    vi.mocked(fetchList).mockResolvedValue(followList)
    const queryClient = new QueryClient()
    mountWith(queryClient, () => {
      useListQuery(9)
    })
    await flushPromises()

    const query = queryClient.getQueryCache().find({
      queryKey:
        _name === 'followers'
          ? queryKeys.followers.followersList(9)
          : queryKeys.followers.followingList(9),
    })
    expect((query?.options as { staleTime?: number } | undefined)?.staleTime).toBe(60_000)
  })

  it('seeds the public-profile cache, so its rows read profiles without a request', async () => {
    vi.mocked(fetchList).mockResolvedValue(followList)
    const queryClient = new QueryClient()
    mountWith(queryClient, () => {
      useListQuery(9)
    })
    await flushPromises()

    expect(queryClient.getQueryData(queryKeys.users.publicProfile(3))).toEqual(ada)
    // A user the server left out is cached as "not found" rather than looked up per row.
    expect(queryClient.getQueryData(queryKeys.users.publicProfile(4))).toBeNull()
    expect(queryClient.getQueryState(queryKeys.users.publicProfile(4))?.status).toBe('success')
  })

  it('means a row mounted afterwards makes no profile request', async () => {
    vi.mocked(fetchList).mockResolvedValue(followList)
    const queryClient = new QueryClient()
    mountWith(queryClient, () => {
      useListQuery(9)
    })
    await flushPromises()
    wrapper?.unmount()

    let row: ReturnType<typeof usePublicUserQuery> | undefined
    mountWith(queryClient, () => {
      row = usePublicUserQuery(3)
      usePublicUserQuery(4)
    })
    await flushPromises()

    expect(row?.data.value).toEqual(ada)
    expect(fetchPublicUser).not.toHaveBeenCalled()
  })
})
