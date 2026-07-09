<script setup lang="ts">
import { computed, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { Activity as ActivityIcon, Plus, RefreshCw, Users as UsersIcon } from '@lucide/vue'
import type { LucideIcon } from '@lucide/vue'

import HomeProfileCard from '@/features/home/components/HomeProfileCard.vue'
import UserDistanceStats from '@/features/home/components/UserDistanceStats.vue'
import UserGoalResults from '@/features/home/components/UserGoalResults.vue'
import HomeActivityCard from '@/features/home/components/HomeActivityCard.vue'
import HomeActivityCardSkeleton from '@/features/home/components/HomeActivityCardSkeleton.vue'
import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
import { EmptyState } from '@/components/ui/empty-state'
import { ErrorState } from '@/components/ui/error-state'
import { Skeleton } from '@/components/ui/skeleton'
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { cn } from '@/lib/utils'
import { useToasts } from '@/composables/useToasts'
import { useInfiniteScroll } from '@/composables/useInfiniteScroll'
import { useCurrentUser } from '@/features/auth/composables/useCurrentUser'
import { useDisplayUnits } from '@/features/activities/composables/useActivityDetail'
import { ACTIVITY_FILE_EXTENSIONS } from '@/features/upload/types'
import { useUploadActivityFileMutation } from '@/features/upload/composables/useUpload'
import {
  useActivityStatsQuery,
  useFollowersActivitiesFeed,
  useGoalResultsQuery,
  useRefreshActivitiesMutation,
  useUserActivitiesFeed,
} from '@/features/home/composables/useHome'

const { t } = useI18n()
const toasts = useToasts()

const { data: currentUser } = useCurrentUser()
const units = useDisplayUnits()
const currentUserId = computed(() => currentUser.value?.id ?? null)

/** Whether the viewer can pull fresh activities from a linked integration. */
const canRefresh = computed(
  () => !!currentUser.value?.isStravaLinked || !!currentUser.value?.isGarminConnectLinked,
)

// --- Distance stats (left) ---
const weekStats = useActivityStatsQuery(currentUserId, 'week')
const monthStats = useActivityStatsQuery(currentUserId, 'month')

// --- Goal results (right) ---
const goalResults = useGoalResultsQuery()

// --- Feed (center) ---
type FeedScope = 'mine' | 'following'
const scope = ref<FeedScope>('mine')

/** The feed-scope tab options, in display order. */
const SCOPE_OPTIONS: ReadonlyArray<{ value: FeedScope; labelKey: string; icon: LucideIcon }> = [
  { value: 'mine', labelKey: 'home.feed.myActivities', icon: ActivityIcon },
  { value: 'following', labelKey: 'home.feed.following', icon: UsersIcon },
]

/**
 * String proxy for the Tabs primitive, whose model is a plain `string`. Reads
 * and writes flow through the typed `scope` ref so the rest of the view keeps
 * full `FeedScope` narrowing; unknown values are ignored.
 */
const scopeModel = computed<string>({
  get: () => scope.value,
  set: (value) => {
    const match = SCOPE_OPTIONS.find((option) => option.value === value)
    if (match) {
      scope.value = match.value
    }
  },
})

const mine = useUserActivitiesFeed(currentUserId, undefined, () => scope.value === 'mine')
const following = useFollowersActivitiesFeed(
  currentUserId,
  undefined,
  () => scope.value === 'following',
)

const activities = computed(
  () => (scope.value === 'mine' ? mine.data.value : following.data.value)?.pages.flat() ?? [],
)
const isPending = computed(() =>
  scope.value === 'mine' ? mine.isPending.value : following.isPending.value,
)
const isError = computed(() =>
  scope.value === 'mine' ? mine.isError.value : following.isError.value,
)
const hasNextPage = computed(() =>
  scope.value === 'mine' ? mine.hasNextPage.value : following.hasNextPage.value,
)
const isFetchingNextPage = computed(() =>
  scope.value === 'mine' ? mine.isFetchingNextPage.value : following.isFetchingNextPage.value,
)
const isEmpty = computed(() => !isPending.value && !isError.value && activities.value.length === 0)

/** Fetches the next page of whichever feed is active. */
function fetchNextPage(): void {
  if (scope.value === 'mine') {
    void mine.fetchNextPage()
  } else {
    void following.fetchNextPage()
  }
}

/** Refetches the active feed after an error. */
function refetchFeed(): void {
  if (scope.value === 'mine') {
    void mine.refetch()
  } else {
    void following.refetch()
  }
}

const sentinel = ref<HTMLElement | null>(null)
useInfiniteScroll(sentinel, () => fetchNextPage(), {
  enabled: () => hasNextPage.value && !isFetchingNextPage.value,
})

// --- Add activity (file upload) ---
const fileInput = ref<HTMLInputElement | null>(null)
const uploadMutation = useUploadActivityFileMutation()
const acceptedFileTypes = ACTIVITY_FILE_EXTENSIONS.map((ext) => `.${ext}`).join(',')

/**
 * Whether to show a placeholder card at the top of the viewer's own feed while
 * an upload is in flight. Scoped to the "mine" feed because that is where the
 * new activity is pinned to the top once the upload resolves.
 */
const showUploadPlaceholder = computed(
  () => scope.value === 'mine' && uploadMutation.isPending.value,
)

/** Opens the hidden file picker. */
function pickFile(): void {
  fileInput.value?.click()
}

/** Uploads the chosen file, surfacing the outcome as a toast. */
function onFileChange(event: Event): void {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]
  input.value = ''
  if (!file) {
    return
  }
  uploadMutation.mutate(file, {
    onSuccess: () => toasts.success(t('home.upload.success')),
    onError: () => toasts.error(t('home.upload.error')),
  })
}

// --- Refresh integrations ---
const refreshMutation = useRefreshActivitiesMutation()

/** Pulls fresh activities from the viewer's linked integrations. */
function onRefresh(): void {
  refreshMutation.mutate(undefined, {
    onSuccess: () => toasts.success(t('home.refresh.success')),
    onError: () => toasts.error(t('home.refresh.error')),
  })
}
</script>

<template>
  <div class="grid grid-cols-1 gap-3 lg:grid-cols-12">
    <!-- Left sidebar -->
    <aside class="flex flex-col gap-3 lg:col-span-3">
      <!-- Profile (photo + username) — hidden on small screens. -->
      <div class="hidden lg:block">
        <HomeProfileCard
          v-if="currentUser"
          :name="currentUser.name"
          :username="currentUser.username"
          :avatar-url="currentUser.avatarUrl"
        />
        <Card v-else class="flex flex-col items-center gap-3">
          <Skeleton class="size-20 rounded-full" />
          <Skeleton class="h-5 w-32" />
          <Skeleton class="h-4 w-24" />
        </Card>
      </div>

      <!-- Actions -->
      <Card class="flex flex-col gap-2">
        <Button :disabled="uploadMutation.isPending.value" @click="pickFile">
          <Plus class="size-4" aria-hidden="true" />
          {{ uploadMutation.isPending.value ? t('home.upload.uploading') : t('home.addActivity') }}
        </Button>
        <Button
          v-if="canRefresh"
          variant="outline"
          :disabled="refreshMutation.isPending.value"
          @click="onRefresh"
        >
          <RefreshCw
            :class="cn('size-4', refreshMutation.isPending.value && 'animate-spin')"
            aria-hidden="true"
          />
          {{
            refreshMutation.isPending.value ? t('home.refresh.refreshing') : t('home.refresh.label')
          }}
        </Button>
        <input
          ref="fileInput"
          type="file"
          class="hidden"
          :accept="acceptedFileTypes"
          @change="onFileChange"
        />
      </Card>

      <!-- Distance stats — hidden on small screens. -->
      <div class="hidden lg:block">
        <UserDistanceStats
          :week-stats="weekStats.data.value"
          :month-stats="monthStats.data.value"
          :units="units"
          :is-loading="weekStats.isLoading.value || monthStats.isLoading.value"
        />
      </div>
    </aside>

    <!-- Center feed -->
    <section class="flex flex-col gap-3 lg:col-span-6">
      <!-- Scope toggle -->
      <Tabs v-model="scopeModel">
        <TabsList class="grid w-full grid-cols-2" :aria-label="t('home.feed.scopeLabel')">
          <TabsTrigger
            v-for="option in SCOPE_OPTIONS"
            :key="option.value"
            :value="option.value"
            class="gap-1.5"
          >
            <component :is="option.icon" class="size-4" aria-hidden="true" />
            {{ t(option.labelKey) }}
          </TabsTrigger>
        </TabsList>
      </Tabs>

      <!-- Loading -->
      <div v-if="isPending" class="flex flex-col gap-3" aria-busy="true">
        <HomeActivityCardSkeleton v-for="n in 3" :key="n" />
      </div>

      <!-- Error -->
      <ErrorState
        v-else-if="isError"
        :title="t('home.feed.error.title')"
        :description="t('home.feed.error.description')"
        @retry="refetchFeed"
      >
        <template #action="{ retry }">
          <Button variant="outline" @click="retry">{{ t('home.feed.error.retry') }}</Button>
        </template>
      </ErrorState>

      <!-- Empty -->
      <EmptyState
        v-else-if="isEmpty && !showUploadPlaceholder"
        :title="
          scope === 'mine' ? t('home.feed.empty.mine.title') : t('home.feed.empty.following.title')
        "
        :description="
          scope === 'mine'
            ? t('home.feed.empty.mine.description')
            : t('home.feed.empty.following.description')
        "
      >
        <template #icon>
          <ActivityIcon class="size-8" aria-hidden="true" />
        </template>
      </EmptyState>

      <!-- Feed -->
      <template v-else>
        <!-- Placeholder for an activity currently being uploaded. -->
        <HomeActivityCardSkeleton v-if="showUploadPlaceholder" />

        <HomeActivityCard
          v-for="activity in activities"
          :key="activity.id"
          :activity="activity"
          :units="units"
          :current-user-id="currentUserId"
        />

        <!-- Infinite-scroll sentinel + accessible manual fallback. -->
        <div v-if="hasNextPage" ref="sentinel" class="flex justify-center">
          <Button variant="ghost" :disabled="isFetchingNextPage" @click="fetchNextPage">
            {{ isFetchingNextPage ? t('home.feed.loading') : t('home.feed.loadMore') }}
          </Button>
        </div>
      </template>
    </section>

    <!-- Right sidebar (hidden on small screens, matching v1). -->
    <aside class="hidden flex-col gap-3 lg:col-span-3 lg:flex">
      <UserGoalResults
        :goals="goalResults.data.value ?? []"
        :units="units"
        :is-loading="goalResults.isLoading.value"
      />
    </aside>
  </div>
</template>
