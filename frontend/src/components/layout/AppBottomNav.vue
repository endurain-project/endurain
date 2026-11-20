<script setup lang="ts">
import { computed } from 'vue'
import { RouterLink } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { Bell, Bike, Heart, House, Menu, type LucideIcon } from '@lucide/vue'

import { useUnreadNotificationsCount } from '@/features/notifications/composables/useNotifications'
import { useAuthStore } from '@/features/auth/stores/auth'

interface BottomNavLink {
  name: string
  label: string
  icon: LucideIcon
}

const { t } = useI18n()
const auth = useAuthStore()
const { data: unreadCount } = useUnreadNotificationsCount()

/** Whether the alerts tab shows its unread indicator dot. */
const hasUnread = computed(() => (unreadCount.value ?? 0) > 0)

/** Accessible alerts label, folding in the unread count when present. */
const alertsLabel = computed(() =>
  hasUnread.value ? t('notifications.badge', { count: unreadCount.value ?? 0 }) : t('nav.alerts'),
)

/**
 * Leading destinations of the mobile bottom bar. Alerts and Menu render separately because they
 * carry an unread indicator / fixed destination.
 */
const links = computed<BottomNavLink[]>(() => [
  { name: 'home', label: t('nav.home'), icon: House },
  { name: 'gears', label: t('nav.gear'), icon: Bike },
  { name: 'health', label: t('nav.health'), icon: Heart },
])
</script>

<template>
  <!--
    Mobile primary navigation. A sticky bar
    pinned to the bottom on small screens (Home, Gear, Health, Alerts, Menu),
    hidden from `lg` up where the top navbar takes over. Authenticated only.
  -->
  <nav
    v-if="auth.isAuthenticated"
    class="sticky bottom-0 z-40 flex items-stretch justify-around border-t border-border bg-card pb-safe lg:hidden"
    :aria-label="t('nav.primary')"
  >
    <RouterLink
      v-for="link in links"
      :key="link.name"
      :to="{ name: link.name }"
      class="flex flex-1 flex-col items-center gap-1 px-1 py-2 text-micro text-muted-foreground hover:text-foreground"
      active-class="text-foreground"
    >
      <component :is="link.icon" class="size-5" />
      <span class="truncate">{{ link.label }}</span>
    </RouterLink>

    <RouterLink
      :to="{ name: 'notifications' }"
      class="flex flex-1 flex-col items-center gap-1 px-1 py-2 text-micro text-muted-foreground hover:text-foreground"
      active-class="text-foreground"
      :aria-label="alertsLabel"
    >
      <span class="relative">
        <Bell class="size-5" />
        <span
          v-if="hasUnread"
          class="absolute -end-0.5 -top-0.5 size-2 rounded-full bg-brand"
          aria-hidden="true"
        />
      </span>
      <span class="truncate">{{ t('nav.alerts') }}</span>
    </RouterLink>

    <RouterLink
      :to="{ name: 'menu' }"
      class="flex flex-1 flex-col items-center gap-1 px-1 py-2 text-micro text-muted-foreground hover:text-foreground"
      active-class="text-foreground"
    >
      <Menu class="size-5" />
      <span class="truncate">{{ t('nav.menu') }}</span>
    </RouterLink>
  </nav>
</template>
