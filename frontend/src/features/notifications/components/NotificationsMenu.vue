<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { RouterLink, useRoute } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { ArrowRight, Bell, BellOff, CheckCheck } from '@lucide/vue'

import NotificationItem from '@/features/notifications/components/NotificationItem.vue'
import { Button } from '@/components/ui/button'
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover'
import { Skeleton } from '@/components/ui/skeleton'
import { useCurrentUser } from '@/features/auth/composables/useCurrentUser'
import {
  useMarkAllNotificationsReadMutation,
  useMarkNotificationReadMutation,
  useNotificationsQuery,
  useUnreadNotificationsCount,
} from '@/features/notifications/composables/useNotifications'

/** Number of recent notifications shown in the dropdown preview. */
const PREVIEW_SIZE = 6

const { t } = useI18n()
const route = useRoute()
const { data: currentUser } = useCurrentUser()
const { data: unreadCount } = useUnreadNotificationsCount()
const { data, isPending, isError, refetch } = useNotificationsQuery(() => ({
  numRecords: PREVIEW_SIZE,
}))
const markReadMutation = useMarkNotificationReadMutation()
const markAllReadMutation = useMarkAllNotificationsReadMutation()

/** Controlled open state so navigation can dismiss the panel. */
const open = ref(false)

/** Recent notifications backing the preview list. */
const notifications = computed(() => data.value ?? [])
const isEmpty = computed(
  () => !isPending.value && !isError.value && notifications.value.length === 0,
)

/** Whether the user has any unread notifications; drives badge + bulk action. */
const hasUnread = computed(() => (unreadCount.value ?? 0) > 0)

/** Clamped unread count for the bell badge; empty when nothing is unread. */
const unreadBadge = computed(() => {
  const count = unreadCount.value ?? 0
  if (count <= 0) {
    return ''
  }
  return count > 9 ? '9+' : String(count)
})

/** Accessible label for the bell, folding the unread count in when present. */
const bellLabel = computed(() =>
  hasUnread.value
    ? t('notifications.badge', { count: unreadCount.value ?? 0 })
    : t('notifications.navLabel'),
)

// Close the panel whenever the route changes — covers both a notification's
// deep-link click and the "see all" link, without auto-marking anything read.
watch(
  () => route.fullPath,
  () => {
    open.value = false
  },
)

// The preview does not poll (the badge already does), so opening the panel refetches it: a push
// that was lost never leaves stale rows in front of the user.
watch(open, (isOpen) => {
  if (isOpen) {
    void refetch()
  }
})

/** Optimistically marks one notification read (explicit action, never on open). */
function onMarkRead(id: number): void {
  markReadMutation.mutate(id)
}

/** Optimistically marks every notification read through the bulk mutation. */
function onMarkAllRead(): void {
  markAllReadMutation.mutate()
}

/** Refetches the preview after an error. */
function refetchList(): void {
  void refetch()
}
</script>

<template>
  <Popover v-model:open="open">
    <PopoverTrigger
      class="relative inline-flex cursor-pointer items-center justify-center rounded-input p-2 text-muted-foreground hover:bg-accent hover:text-accent-foreground focus:outline-none focus-visible:ring-3 focus-visible:ring-ring/30 data-[state=open]:bg-accent data-[state=open]:text-accent-foreground"
      :aria-label="bellLabel"
    >
      <Bell class="size-5" />
      <span
        v-if="unreadBadge"
        class="absolute -end-0.5 -top-0.5 inline-flex min-w-4 items-center justify-center rounded-full bg-brand px-1 text-micro font-medium leading-4 text-white"
        aria-hidden="true"
      >
        {{ unreadBadge }}
      </span>
    </PopoverTrigger>

    <PopoverContent
      align="end"
      :side-offset="8"
      class="w-80 max-w-[calc(100vw-1rem)] overflow-hidden p-0"
    >
      <!-- Header: title + explicit "mark all as read" (no mark-on-open). -->
      <div class="flex items-center justify-between gap-2 border-b border-border px-4 py-3">
        <p class="font-medium text-foreground">{{ t('notifications.title') }}</p>
        <Button
          v-if="hasUnread"
          variant="ghost"
          size="sm"
          :disabled="markAllReadMutation.isPending.value"
          @click="onMarkAllRead"
        >
          <CheckCheck class="size-4" aria-hidden="true" />
          {{ t('notifications.markAllRead') }}
        </Button>
      </div>

      <!-- Loading: skeleton rows mirroring the item layout. -->
      <div v-if="isPending" class="divide-y divide-border" aria-busy="true">
        <div v-for="n in 4" :key="n" class="flex items-start gap-3 px-4 py-3">
          <Skeleton class="size-5 shrink-0 rounded-full" />
          <div class="flex-1 space-y-2">
            <Skeleton class="h-4 w-1/3" />
            <Skeleton class="h-3 w-2/3" />
          </div>
        </div>
      </div>

      <!-- Error -->
      <div v-else-if="isError" class="flex flex-col items-center gap-2 px-4 py-8 text-center">
        <p class="text-body">{{ t('notifications.error.title') }}</p>
        <Button variant="outline" size="sm" @click="refetchList">
          {{ t('notifications.error.retry') }}
        </Button>
      </div>

      <!-- Empty -->
      <div v-else-if="isEmpty" class="flex flex-col items-center gap-2 px-4 py-8 text-center">
        <BellOff class="size-7 text-muted-foreground" aria-hidden="true" />
        <p class="text-body">{{ t('notifications.empty.title') }}</p>
      </div>

      <!-- List -->
      <ul v-else class="max-h-96 divide-y divide-border overflow-y-auto">
        <li v-for="item in notifications" :key="item.id">
          <NotificationItem
            :notification="item"
            :current-user-id="currentUser?.id"
            @mark-read="onMarkRead"
          />
        </li>
      </ul>

      <!-- Footer: optional jump to the full notifications view. -->
      <div class="border-t border-border p-1">
        <RouterLink
          :to="{ name: 'notifications' }"
          class="flex items-center justify-center gap-1.5 rounded-input px-3 py-2 text-sm font-medium text-primary hover:bg-accent"
        >
          {{ t('notifications.seeAll') }}
          <ArrowRight class="size-4" aria-hidden="true" />
        </RouterLink>
      </div>
    </PopoverContent>
  </Popover>
</template>
