<script setup lang="ts">
import { computed, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { RouterLink, useRoute } from 'vue-router'
import { Activity as ActivityIcon, Settings, UserX } from '@lucide/vue'

import UserProfileHeader from '@/features/users/components/UserProfileHeader.vue'
import FollowButton from '@/features/followers/components/FollowButton.vue'
import FollowerListItem from '@/features/followers/components/FollowerListItem.vue'
import UserDistanceStats from '@/features/home/components/UserDistanceStats.vue'
import UserGoalResults from '@/features/home/components/UserGoalResults.vue'
import HomeActivityCard from '@/features/home/components/HomeActivityCard.vue'
import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
import { EmptyState } from '@/components/ui/empty-state'
import { ErrorState } from '@/components/ui/error-state'
import { Skeleton } from '@/components/ui/skeleton'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { useCurrentUser } from '@/features/auth/composables/useCurrentUser'
import { useDisplayUnits } from '@/features/activities/composables/useActivityDetail'
import { shiftWeeks, todayIsoDate, weekEnd, weekStart } from '@/utils/datetime'
import { usePublicUserQuery } from '@/features/users/composables/usePublicUser'
import {
  useActivityStatsQuery,
  useGoalResultsQuery,
  useUserMonthlyActivityCountQuery,
  useUserWeekActivitiesQuery,
} from '@/features/home/composables/useHome'
import {
  useFollowersCountQuery,
  useFollowersQuery,
  useFollowingCountQuery,
  useFollowingQuery,
} from '@/features/followers/composables/useFollowers'

type TabKey = 'activities' | 'following' | 'followers'

const route = useRoute()
const { t } = useI18n()

const { data: currentUser } = useCurrentUser()
const units = useDisplayUnits()
const currentUserId = computed(() => currentUser.value?.id ?? null)
const firstDayOfWeek = computed(() => currentUser.value?.firstDayOfWeek ?? 'monday')

/** The profile owner's id from the route, or `null` when the param is invalid. */
const profileId = computed(() => {
  const raw = Number(route.params.id)
  return Number.isFinite(raw) && raw > 0 ? raw : null
})

/** Whether the viewer is looking at their own profile. */
const isSelf = computed(
  () => currentUserId.value !== null && currentUserId.value === profileId.value,
)

const userQuery = usePublicUserQuery(profileId)
const user = computed(() => userQuery.data.value ?? null)

// --- Sidebar stats ---
const weekStats = useActivityStatsQuery(profileId, 'week')
const monthStats = useActivityStatsQuery(profileId, 'month')
const monthCount = useUserMonthlyActivityCountQuery(profileId)
const followersCount = useFollowersCountQuery(profileId)
const followingCount = useFollowingCountQuery(profileId)

// --- Sidebar goals (own profile only; the backend scopes goals to the viewer) ---
const goalResults = useGoalResultsQuery(() => isSelf.value)

// --- Tabs ---
const initialTab: TabKey =
  route.query.tab === 'followers' || route.query.tab === 'following'
    ? route.query.tab
    : 'activities'
// reka-ui's Tabs model is a plain string, so keep the ref widened to `string`.
const activeTab = ref<string>(initialTab)

/** Refetches the public user after a load error. */
function refetchUser(): void {
  void userQuery.refetch()
}

// --- Activities (week-by-week browser, v1 parity) ---
/** Number of past weeks reachable as dated buttons before the oldest bucket. */
const TOTAL_WEEKS = 50
/** The "one year ago" bucket index (everything older than {@link TOTAL_WEEKS}). */
const OLDEST_WEEK = 51
/** Selected week offset: 0 = this week, 1..50 = prior weeks, 51 = one year ago. */
const week = ref(0)

const weekActivitiesQuery = useUserWeekActivitiesQuery(
  profileId,
  week,
  () => activeTab.value === 'activities',
)
const activities = computed(() => weekActivitiesQuery.data.value ?? [])
const activitiesEmpty = computed(
  () =>
    !weekActivitiesQuery.isPending.value &&
    !weekActivitiesQuery.isError.value &&
    activities.value.length === 0,
)

/** The window of dated week buttons shown around the selected week. */
const visibleWeeks = computed(() => {
  const start = Math.max(1, week.value - 1)
  const end = Math.min(TOTAL_WEEKS, week.value + 1)
  return Array.from({ length: end - start + 1 }, (_, index) => index + start)
})

/** Selects a week offset; the activities query refetches reactively. */
function setWeek(value: number): void {
  week.value = value
}

/** Formats a week offset as its configured `DD/MM-DD/MM` range. */
function formatWeekRange(weekNumber: number): string {
  const currentWeekStart = weekStart(todayIsoDate(), firstDayOfWeek.value)
  const startOfWeek = shiftWeeks(currentWeekStart, -weekNumber)
  const endOfWeek = weekEnd(startOfWeek, firstDayOfWeek.value)
  const formatDate = (iso: string): string => `${iso.slice(8, 10)}/${iso.slice(5, 7)}`
  return `${formatDate(startOfWeek)}-${formatDate(endOfWeek)}`
}

/** Refetches the current week's activities after an error. */
function refetchActivities(): void {
  void weekActivitiesQuery.refetch()
}

// --- Following / followers lists ---
const followingQuery = useFollowingQuery(profileId)
const followersQuery = useFollowersQuery(profileId)
const followingEdges = computed(() => followingQuery.data.value ?? [])
const followerEdges = computed(() => followersQuery.data.value ?? [])

/** Refetches the following list after an error. */
function refetchFollowing(): void {
  void followingQuery.refetch()
}

/** Refetches the followers list after an error. */
function refetchFollowers(): void {
  void followersQuery.refetch()
}
</script>

<template>
  <!-- Loading -->
  <div v-if="userQuery.isPending.value" class="grid grid-cols-1 gap-3 lg:grid-cols-12">
    <aside class="flex flex-col gap-3 lg:col-span-3">
      <Card class="flex flex-col items-center gap-3">
        <Skeleton class="size-24 rounded-full" />
        <Skeleton class="h-5 w-32" />
        <Skeleton class="h-4 w-24" />
      </Card>
      <Card><Skeleton class="h-16 w-full" /></Card>
    </aside>
    <section class="flex flex-col gap-3 lg:col-span-9">
      <Card v-for="n in 2" :key="n"><Skeleton class="h-40 w-full" /></Card>
    </section>
  </div>

  <!-- Error -->
  <ErrorState
    v-else-if="userQuery.isError.value"
    :title="t('userProfile.error.title')"
    :description="t('userProfile.error.description')"
    @retry="refetchUser"
  >
    <template #action="{ retry }">
      <Button variant="outline" @click="retry">{{ t('userProfile.error.retry') }}</Button>
    </template>
  </ErrorState>

  <!-- Not found -->
  <EmptyState
    v-else-if="!user"
    :title="t('userProfile.notFound.title')"
    :description="t('userProfile.notFound.description')"
  >
    <template #icon>
      <UserX class="size-8" aria-hidden="true" />
    </template>
  </EmptyState>

  <!-- Profile -->
  <div v-else class="grid grid-cols-1 gap-3 lg:grid-cols-12">
    <!-- Sidebar -->
    <aside class="flex flex-col gap-3 lg:col-span-3">
      <UserProfileHeader :user="user" />

      <Card class="flex flex-col gap-2">
        <Button v-if="isSelf" as-child variant="outline" class="w-full">
          <RouterLink :to="{ name: 'settings-profile' }">
            <Settings class="size-4" aria-hidden="true" />
            {{ t('userProfile.editProfile') }}
          </RouterLink>
        </Button>
        <FollowButton v-else :target-user-id="user.id" :target-name="user.name" />
      </Card>

      <!-- Summary counts -->
      <Card class="flex flex-col gap-3">
        <div class="text-center">
          <p class="text-metric">{{ monthCount.data.value ?? 0 }}</p>
          <p class="text-caption">{{ t('userProfile.stats.thisMonth') }}</p>
        </div>
        <div class="grid grid-cols-2 gap-2 border-t border-border pt-3 text-center">
          <button type="button" class="cursor-pointer" @click="activeTab = 'following'">
            <p class="text-metric">{{ followingCount.data.value ?? 0 }}</p>
            <p class="text-caption">{{ t('userProfile.stats.following') }}</p>
          </button>
          <button type="button" class="cursor-pointer" @click="activeTab = 'followers'">
            <p class="text-metric">{{ followersCount.data.value ?? 0 }}</p>
            <p class="text-caption">{{ t('userProfile.stats.followers') }}</p>
          </button>
        </div>
      </Card>

      <UserDistanceStats
        :week-stats="weekStats.data.value"
        :month-stats="monthStats.data.value"
        :units="units"
        :is-loading="weekStats.isLoading.value || monthStats.isLoading.value"
      />

      <UserGoalResults
        v-if="isSelf"
        :goals="goalResults.data.value ?? []"
        :units="units"
        :is-loading="goalResults.isLoading.value"
      />
    </aside>

    <!-- Content -->
    <section class="lg:col-span-9">
      <Tabs v-model="activeTab" class="flex flex-col">
        <TabsList class="grid grid-cols-3">
          <TabsTrigger value="activities">{{ t('userProfile.tabs.activities') }}</TabsTrigger>
          <TabsTrigger value="following">{{ t('userProfile.tabs.following') }}</TabsTrigger>
          <TabsTrigger value="followers">{{ t('userProfile.tabs.followers') }}</TabsTrigger>
        </TabsList>

        <!-- Activities (week-by-week browser) -->
        <TabsContent value="activities" class="flex flex-col gap-3">
          <!-- Week pagination -->
          <Card>
            <nav
              class="flex flex-wrap items-center justify-center gap-1"
              :aria-label="t('userProfile.activities.weekNav')"
            >
              <Button size="sm" :variant="week === 0 ? 'default' : 'outline'" @click="setWeek(0)">
                {{ t('userProfile.activities.thisWeek') }}
              </Button>
              <span v-if="week > 2" class="px-1 text-hint" aria-hidden="true">…</span>
              <Button
                v-for="w in visibleWeeks"
                :key="w"
                size="sm"
                :variant="w === week ? 'default' : 'outline'"
                @click="setWeek(w)"
              >
                {{ formatWeekRange(w) }}
              </Button>
              <span v-if="week < OLDEST_WEEK - 2" class="px-1 text-hint" aria-hidden="true">…</span>
              <Button
                size="sm"
                :variant="week === OLDEST_WEEK ? 'default' : 'outline'"
                @click="setWeek(OLDEST_WEEK)"
              >
                {{ t('userProfile.activities.oneYearAgo') }}
              </Button>
            </nav>
          </Card>

          <div
            v-if="weekActivitiesQuery.isPending.value"
            class="flex flex-col gap-3"
            aria-busy="true"
          >
            <Card v-for="n in 3" :key="n" class="flex flex-col gap-3">
              <div class="flex items-center gap-3">
                <Skeleton class="size-11 rounded-full" />
                <div class="flex-1 space-y-2">
                  <Skeleton class="h-4 w-1/3" />
                  <Skeleton class="h-3 w-1/2" />
                </div>
              </div>
              <Skeleton class="h-48 w-full rounded-card" />
            </Card>
          </div>

          <ErrorState
            v-else-if="weekActivitiesQuery.isError.value"
            :title="t('userProfile.activitiesError.title')"
            :description="t('userProfile.activitiesError.description')"
            @retry="refetchActivities"
          >
            <template #action="{ retry }">
              <Button variant="outline" @click="retry">
                {{ t('userProfile.activitiesError.retry') }}
              </Button>
            </template>
          </ErrorState>

          <EmptyState
            v-else-if="activitiesEmpty"
            :title="
              isSelf
                ? t('userProfile.empty.activities.ownTitle')
                : t('userProfile.empty.activities.otherTitle')
            "
            :description="isSelf ? t('userProfile.empty.activities.ownDescription') : undefined"
          >
            <template #icon>
              <ActivityIcon class="size-8" aria-hidden="true" />
            </template>
          </EmptyState>

          <template v-else>
            <HomeActivityCard
              v-for="activity in activities"
              :key="activity.id"
              :activity="activity"
              :units="units"
              :current-user-id="currentUserId"
            />
          </template>
        </TabsContent>

        <!-- Following -->
        <TabsContent value="following" class="flex flex-col gap-3">
          <Card>
            <div v-if="followingQuery.isPending.value" class="flex flex-col gap-3" aria-busy="true">
              <div v-for="n in 4" :key="n" class="flex items-center gap-3">
                <Skeleton class="size-11 rounded-full" />
                <div class="flex-1 space-y-2">
                  <Skeleton class="h-4 w-1/3" />
                  <Skeleton class="h-3 w-1/4" />
                </div>
              </div>
            </div>

            <ErrorState
              v-else-if="followingQuery.isError.value"
              :title="t('userProfile.listError.title')"
              :description="t('userProfile.listError.description')"
              @retry="refetchFollowing"
            >
              <template #action="{ retry }">
                <Button variant="outline" @click="retry">
                  {{ t('userProfile.listError.retry') }}
                </Button>
              </template>
            </ErrorState>

            <EmptyState
              v-else-if="followingEdges.length === 0"
              variant="filtered"
              :title="
                isSelf
                  ? t('userProfile.empty.following.ownTitle')
                  : t('userProfile.empty.following.otherTitle')
              "
            />

            <ul v-else class="flex flex-col gap-3">
              <li v-for="edge in followingEdges" :key="edge.userId">
                <FollowerListItem
                  :user-id="edge.userId"
                  :is-accepted="edge.isAccepted"
                  relation="following"
                  :can-manage="isSelf"
                />
              </li>
            </ul>
          </Card>
        </TabsContent>

        <!-- Followers -->
        <TabsContent value="followers" class="flex flex-col gap-3">
          <Card>
            <div v-if="followersQuery.isPending.value" class="flex flex-col gap-3" aria-busy="true">
              <div v-for="n in 4" :key="n" class="flex items-center gap-3">
                <Skeleton class="size-11 rounded-full" />
                <div class="flex-1 space-y-2">
                  <Skeleton class="h-4 w-1/3" />
                  <Skeleton class="h-3 w-1/4" />
                </div>
              </div>
            </div>

            <ErrorState
              v-else-if="followersQuery.isError.value"
              :title="t('userProfile.listError.title')"
              :description="t('userProfile.listError.description')"
              @retry="refetchFollowers"
            >
              <template #action="{ retry }">
                <Button variant="outline" @click="retry">
                  {{ t('userProfile.listError.retry') }}
                </Button>
              </template>
            </ErrorState>

            <EmptyState
              v-else-if="followerEdges.length === 0"
              variant="filtered"
              :title="
                isSelf
                  ? t('userProfile.empty.followers.ownTitle')
                  : t('userProfile.empty.followers.otherTitle')
              "
            />

            <ul v-else class="flex flex-col gap-3">
              <li v-for="edge in followerEdges" :key="edge.userId">
                <FollowerListItem
                  :user-id="edge.userId"
                  :is-accepted="edge.isAccepted"
                  relation="follower"
                  :can-manage="isSelf"
                />
              </li>
            </ul>
          </Card>
        </TabsContent>
      </Tabs>
    </section>
  </div>
</template>
