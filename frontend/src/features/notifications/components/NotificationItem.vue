<script setup lang="ts">
import { computed } from 'vue'
import { RouterLink, type RouteLocationRaw, useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { Check, X } from '@lucide/vue'

import type { Notification } from '@/features/notifications/types'

import { Button } from '@/components/ui/button'
import { formatRelativeTime } from '@/utils/datetime'
import { presentNotification } from '@/features/notifications/utils/notificationPresenter'

const props = defineProps<{
  /** The notification to render. */
  notification: Notification
  /** Viewing user's id, used to deep-link follower requests to their list. */
  currentUserId?: number | null
}>()

const emit = defineEmits<{
  /** Request to mark this notification read. */
  markRead: [id: string]
  /** Request to delete this notification. */
  dismiss: [id: string]
}>()

const { t, locale } = useI18n()
const router = useRouter()

const presentation = computed(() =>
  presentNotification(props.notification, {
    currentUserId: props.currentUserId,
    locale: locale.value,
  }),
)

/**
 * The navigation target, but only when its route is actually registered. Deep
 * links to as-yet-unbuilt views (activity/user detail) resolve to `null` here,
 * so the row renders as a non-link until those routes ship — then they light up
 * with no change to this component.
 */
const resolvedTo = computed<RouteLocationRaw | null>(() => {
  const target = presentation.value.to
  if (!target) {
    return null
  }
  if (typeof target === 'object' && 'name' in target && typeof target.name === 'string') {
    return router.hasRoute(target.name) ? target : null
  }
  return target
})

const title = computed(() => t(presentation.value.titleKey))
const body = computed(() => t(presentation.value.bodyKey, presentation.value.bodyParams ?? {}))
const relativeTime = computed(() =>
  formatRelativeTime(props.notification.createdAt, new Date(), locale.value),
)

/** Marks a linked notification read as the viewer navigates into it. */
function onActivate(): void {
  if (resolvedTo.value && !props.notification.read) {
    emit('markRead', props.notification.id)
  }
}
</script>

<template>
  <component
    :is="resolvedTo ? RouterLink : 'div'"
    :to="resolvedTo ?? undefined"
    class="flex items-start gap-3 px-4 py-3 transition-colors"
    :class="resolvedTo ? 'cursor-pointer hover:bg-accent' : ''"
    @click="onActivate"
  >
    <component
      :is="presentation.icon"
      class="mt-0.5 size-5 shrink-0 text-muted-foreground"
      aria-hidden="true"
    />

    <div class="min-w-0 flex-1">
      <div class="flex items-center gap-2">
        <p class="truncate font-medium text-foreground">{{ title }}</p>
        <span
          v-if="!notification.read"
          class="size-2 shrink-0 rounded-full bg-brand"
          role="status"
          :aria-label="t('notifications.unread')"
        />
      </div>
      <p v-if="body" class="text-body">{{ body }}</p>
      <p v-if="relativeTime" class="mt-0.5 text-hint">{{ relativeTime }}</p>
    </div>

    <div class="flex shrink-0 items-center gap-1">
      <button
        v-if="!notification.read"
        type="button"
        class="inline-flex size-8 shrink-0 items-center justify-center rounded-input text-muted-foreground hover:bg-accent hover:text-accent-foreground focus-visible:outline-none focus-visible:ring-3 focus-visible:ring-ring/30"
        :aria-label="t('notifications.markRead')"
        @click.stop.prevent="emit('markRead', notification.id)"
      >
        <Check class="size-4" />
      </button>
      <Button
        type="button"
        variant="ghost"
        size="icon-sm"
        class="text-muted-foreground"
        data-testid="notification-dismiss"
        :aria-label="t('notifications.dismiss')"
        :title="t('notifications.dismiss')"
        @click.stop.prevent="emit('dismiss', notification.id)"
      >
        <X aria-hidden="true" />
      </Button>
    </div>
  </component>
</template>
