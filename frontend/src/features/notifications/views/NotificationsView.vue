<script setup lang="ts">
import { computed, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { BellOff, CheckCheck } from '@lucide/vue'

import NotificationItem from '@/features/notifications/components/NotificationItem.vue'
import { Button } from '@/components/ui/button'
import { EmptyState } from '@/components/ui/empty-state'
import { ErrorState } from '@/components/ui/error-state'
import { Skeleton } from '@/components/ui/skeleton'
import { useCurrentUser } from '@/features/auth/composables/useCurrentUser'
import { useToasts } from '@/composables/useToasts'
import { useInfiniteScroll } from '@/composables/useInfiniteScroll'
import {
  useInfiniteNotificationsQuery,
  useDeleteNotificationMutation,
  useMarkAllNotificationsReadMutation,
  useMarkNotificationReadMutation,
} from '@/features/notifications/composables/useNotifications'

const { t } = useI18n()
const { data: currentUser } = useCurrentUser()

const { data, isPending, isError, refetch, fetchNextPage, hasNextPage, isFetchingNextPage } =
  useInfiniteNotificationsQuery()
const markReadMutation = useMarkNotificationReadMutation()
const markAllReadMutation = useMarkAllNotificationsReadMutation()
const deleteMutation = useDeleteNotificationMutation()
const toasts = useToasts()

/** All loaded slices flattened into a single list for rendering. */
const notifications = computed(() => data.value?.pages.flatMap((slice) => slice.items) ?? [])
const isEmpty = computed(
  () => !isPending.value && !isError.value && notifications.value.length === 0,
)

/** Whether any loaded notification is still unread. */
const hasUnread = computed(() => notifications.value.some((item) => !item.read))

// Sentinel for infinite scroll; only mounted while another slice is available,
// so the observer tears down once the list is fully loaded.
const sentinel = ref<HTMLElement | null>(null)
useInfiniteScroll(sentinel, () => void fetchNextPage(), {
  enabled: () => hasNextPage.value && !isFetchingNextPage.value,
})

/** Refetches the list after an error. */
function refetchList(): void {
  void refetch()
}

/** Optimistically marks a notification read through the shared mutation. */
function onMarkRead(id: string): void {
  markReadMutation.mutate(id)
}

/** Deletes one notification; a failure rolls the row back and shows an error toast. */
function onDismiss(id: string): void {
  deleteMutation.mutate(id, { onError: () => toasts.error(t('notifications.dismissError')) })
}

/** Optimistically marks every notification read through the bulk mutation. */
function onMarkAllRead(): void {
  markAllReadMutation.mutate()
}
</script>

<template>
  <section class="flex flex-col 3">
    <header class="flex items-start justify-between gap-3">
      <div class="flex flex-col gap-1">
        <h1 class="text-page-title">{{ t('notifications.title') }}</h1>
        <p class="text-body">{{ t('notifications.subtitle') }}</p>
      </div>
      <Button
        v-if="hasUnread"
        variant="outline"
        size="sm"
        :disabled="markAllReadMutation.isPending.value"
        @click="onMarkAllRead"
      >
        <CheckCheck class="size-4" aria-hidden="true" />
        {{ t('notifications.markAllRead') }}
      </Button>
    </header>

    <div class="overflow-hidden rounded-card border border-border bg-card">
      <!-- Loading: skeleton rows mirroring the item layout. -->
      <div v-if="isPending" class="divide-y divide-border" aria-busy="true">
        <div v-for="n in 6" :key="n" class="flex items-start gap-3 px-4 py-3">
          <Skeleton class="size-5 shrink-0 rounded-full" />
          <div class="flex-1 space-y-2">
            <Skeleton class="h-4 w-1/3" />
            <Skeleton class="h-3 w-2/3" />
          </div>
        </div>
      </div>

      <!-- Error -->
      <ErrorState
        v-else-if="isError"
        :title="t('notifications.error.title')"
        :description="t('notifications.error.description')"
        @retry="refetchList"
      >
        <template #action="{ retry }">
          <Button variant="outline" @click="retry">{{ t('notifications.error.retry') }}</Button>
        </template>
      </ErrorState>

      <!-- Empty -->
      <EmptyState
        v-else-if="isEmpty"
        :title="t('notifications.empty.title')"
        :description="t('notifications.empty.description')"
      >
        <template #icon>
          <BellOff class="size-8" aria-hidden="true" />
        </template>
      </EmptyState>

      <!-- List -->
      <ul v-else class="divide-y divide-border">
        <li v-for="item in notifications" :key="item.id">
          <NotificationItem
            :notification="item"
            :current-user-id="currentUser?.id"
            @mark-read="onMarkRead"
            @dismiss="onDismiss"
          />
        </li>
      </ul>
    </div>

    <!-- Infinite-scroll sentinel + accessible manual fallback. -->
    <div v-if="!isPending && !isError && hasNextPage" ref="sentinel" class="flex justify-center">
      <Button variant="ghost" :disabled="isFetchingNextPage" @click="fetchNextPage()">
        {{ isFetchingNextPage ? t('notifications.loading') : t('notifications.loadMore') }}
      </Button>
    </div>
  </section>
</template>
