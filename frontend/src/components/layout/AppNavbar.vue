<script setup lang="ts">
import { computed } from 'vue'
import { RouterLink, useRoute, type RouteLocationRaw } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { ChevronDown, LogOut, Settings } from '@lucide/vue'

import LocaleSwitcher from '@/components/LocaleSwitcher.vue'
import ThemeToggle from '@/components/ThemeToggle.vue'
import AppLogo from '@/components/AppLogo.vue'
import UserAvatar from '@/components/UserAvatar.vue'
import NotificationsMenu from '@/features/notifications/components/NotificationsMenu.vue'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { Badge } from '@/components/ui/badge'
import { useAppConfig } from '@/features/config/composables/useAppConfig'
import { useCurrentUser } from '@/features/auth/composables/useCurrentUser'
import { useNavigation, type NavLink } from '@/composables/useNavigation'
import { useSignOut } from '@/features/auth/composables/useSignOut'
import { useAuthStore } from '@/features/auth/stores/auth'
import { useUpdateCheck } from '@/features/core/composables/useUpdateCheck'
import { cn } from '@/lib/utils'

const { t } = useI18n()
const { config } = useAppConfig()
const { primaryLinks } = useNavigation()
const auth = useAuthStore()
const { signOut } = useSignOut()
const { data: currentUser } = useCurrentUser()
const route = useRoute()
const { updateAvailable, latestVersion } = useUpdateCheck()

/**
 * Whether a nav entry maps to the active route, so its trigger/link can show
 * the active styling. Grouped entries match when any child route is active;
 * single entries match their own route.
 */
function isLinkActive(link: NavLink): boolean {
  if (link.children?.length) {
    return link.children.some((child) => child.name === route.name)
  }
  return link.name === route.name
}

/**
 * The current user's public profile page. Falls back to profile settings while
 * the user record is still loading so the link target is always valid.
 */
const profileRoute = computed<RouteLocationRaw>(() =>
  currentUser.value
    ? { name: 'user', params: { id: currentUser.value.id } }
    : { name: 'settings-profile' },
)
</script>

<template>
  <header class="sticky top-0 z-40 border-b border-border bg-card pt-safe">
    <div class="mx-auto flex h-14 w-full max-w-7xl items-center gap-3 px-3 sm:px-3">
      <!-- Brand -->
      <RouterLink
        :to="{ name: 'home' }"
        class="flex items-center gap-2 font-medium text-foreground"
      >
        <AppLogo width="24" height="24" class="size-6" />
        <span>{{ config.branding.appName }}</span>
      </RouterLink>

      <!-- Primary nav (desktop, authenticated) -->
      <nav v-if="primaryLinks.length" class="hidden items-center gap-1 lg:flex">
        <template v-for="link in primaryLinks" :key="link.name">
          <!-- Grouped destinations render as a dropdown (e.g. Activities → list + summary). -->
          <DropdownMenu v-if="link.children?.length">
            <DropdownMenuTrigger
              :class="
                cn(
                  'flex cursor-pointer items-center gap-1.5 rounded-input px-3 py-1.5 text-sm hover:bg-accent hover:text-accent-foreground focus:outline-none focus-visible:ring-3 focus-visible:ring-ring/30',
                  isLinkActive(link) ? 'text-foreground' : 'text-muted-foreground',
                )
              "
            >
              <component :is="link.icon" class="size-4" />
              <span>{{ link.label }}</span>
              <ChevronDown class="size-4" />
            </DropdownMenuTrigger>
            <DropdownMenuContent align="start">
              <DropdownMenuItem v-for="child in link.children" :key="child.name" as-child>
                <RouterLink :to="{ name: child.name }">
                  <component :is="child.icon" class="size-4" />
                  <span>{{ child.label }}</span>
                </RouterLink>
              </DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>

          <!-- Single destinations render as a direct link. -->
          <RouterLink
            v-else
            :to="{ name: link.name }"
            :class="
              cn(
                'flex items-center gap-1.5 rounded-input px-3 py-1.5 text-sm hover:bg-accent hover:text-accent-foreground',
                isLinkActive(link) ? 'text-foreground' : 'text-muted-foreground',
              )
            "
          >
            <component :is="link.icon" class="size-4" />
            <span>{{ link.label }}</span>
          </RouterLink>
        </template>
      </nav>

      <!-- Right-aligned controls -->
      <div class="ms-auto flex items-center gap-2">
        <!-- Locale/theme on desktop only; on mobile they live in the menu view. -->
        <div class="hidden items-center gap-2 lg:flex">
          <LocaleSwitcher />
          <ThemeToggle />
        </div>

        <!-- Notifications: the desktop dropdown preview. On mobile the bottom
             nav's Alerts tab is the notifications entry point, so the navbar
             intentionally renders no bell there.
             NotificationsMenu's root is reka-ui's renderless PopoverRoot, so a
             class bound on the component has no element to land on; wrap it so
             the responsive `hidden lg:block` actually hides it on mobile. -->
        <div v-if="auth.isAuthenticated" class="hidden lg:block">
          <NotificationsMenu />
        </div>

        <!-- User menu (the navbar only renders for authenticated users) -->
        <DropdownMenu v-if="auth.isAuthenticated">
          <DropdownMenuTrigger
            class="hidden cursor-pointer list-none items-center gap-2 rounded-input px-2 py-1.5 text-sm text-muted-foreground hover:bg-accent hover:text-accent-foreground focus:outline-none focus-visible:ring-3 focus-visible:ring-ring/30 lg:flex"
            :aria-label="t('nav.userMenu')"
          >
            <UserAvatar :src="currentUser?.avatarUrl" :alt="currentUser?.name" />
            <span
              ><bdi>{{ currentUser?.name }}</bdi></span
            >
            <ChevronDown class="size-4" />
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end">
            <DropdownMenuItem as-child>
              <RouterLink :to="profileRoute">
                <UserAvatar
                  :src="currentUser?.avatarUrl"
                  :alt="currentUser?.name"
                  size-class="size-4"
                />
                <span>{{ t('nav.profile') }}</span>
              </RouterLink>
            </DropdownMenuItem>
            <DropdownMenuItem as-child>
              <RouterLink :to="{ name: 'settings' }">
                <Settings class="size-4" />
                <span>{{ t('nav.settings') }}</span>
                <Badge
                  v-if="updateAvailable"
                  variant="secondary"
                  class="ms-auto border-warning/30 bg-warning/10 text-warning"
                  :title="
                    latestVersion
                      ? t('nav.updateAvailableTitle', { version: latestVersion })
                      : t('nav.updateAvailable')
                  "
                >
                  {{ t('nav.updateAvailable') }}
                </Badge>
              </RouterLink>
            </DropdownMenuItem>
            <DropdownMenuSeparator />
            <DropdownMenuItem @select="signOut">
              <LogOut class="size-4" />
              <span>{{ t('nav.logout') }}</span>
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
      </div>
    </div>
  </header>
</template>
