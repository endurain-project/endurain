<script setup lang="ts">
import { computed } from 'vue'
import { RouterLink, type RouteLocationRaw } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { Activity, Calendar, LogOut, Search, Settings, User } from '@lucide/vue'

import LocaleSwitcher from '@/components/LocaleSwitcher.vue'
import ThemeToggle from '@/components/ThemeToggle.vue'
import AppFooter from '@/components/layout/AppFooter.vue'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
import { useCurrentUser } from '@/features/auth/composables/useCurrentUser'
import { useAuthStore } from '@/features/auth/stores/auth'
import { useSignOut } from '@/features/auth/composables/useSignOut'
import { useUpdateCheck } from '@/features/core/composables/useUpdateCheck'

const { t } = useI18n()
const auth = useAuthStore()
const { signOut } = useSignOut()
const { data: currentUser } = useCurrentUser()
const { updateAvailable, latestVersion } = useUpdateCheck()

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
  <!--
    Mobile-only "Menu" destination reached from the bottom navigation. Mirrors
    the v1 MenuMobileView: stacked, full-width, touch-friendly groups (Search;
    Activities/Summary; Settings/Profile; Logout) plus the footer (which is
    hidden in the main shell on small screens).
  -->
  <section class="flex flex-col gap-3">
    <h1 class="text-page-title">
      {{ t('nav.menu') }}
    </h1>

    <template v-if="auth.isAuthenticated">
      <!-- Search -->
      <Card padding="none" class="overflow-hidden">
        <RouterLink
          :to="{ name: 'search' }"
          class="flex items-center gap-3 px-4 py-3 text-sm text-foreground hover:bg-accent hover:text-accent-foreground"
        >
          <Search class="size-4" />
          <span>{{ t('nav.search') }}</span>
        </RouterLink>
      </Card>

      <!-- Activities / Summary -->
      <Card padding="none" class="overflow-hidden">
        <RouterLink
          :to="{ name: 'activities' }"
          class="flex items-center gap-3 px-4 py-3 text-sm text-foreground hover:bg-accent hover:text-accent-foreground"
        >
          <Activity class="size-4" />
          <span>{{ t('nav.activities') }}</span>
        </RouterLink>
        <hr class="border-border" />
        <RouterLink
          :to="{ name: 'summary' }"
          class="flex items-center gap-3 px-4 py-3 text-sm text-foreground hover:bg-accent hover:text-accent-foreground"
        >
          <Calendar class="size-4" />
          <span>{{ t('nav.summary') }}</span>
        </RouterLink>
      </Card>

      <!-- Settings / Profile -->
      <Card padding="none" class="overflow-hidden">
        <RouterLink
          :to="{ name: 'settings' }"
          class="flex items-center gap-3 px-4 py-3 text-sm text-foreground hover:bg-accent hover:text-accent-foreground"
        >
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
        <hr class="border-border" />
        <RouterLink
          :to="profileRoute"
          class="flex items-center gap-3 px-4 py-3 text-sm text-foreground hover:bg-accent hover:text-accent-foreground"
        >
          <User class="size-4" />
          <span>{{ t('nav.profile') }}</span>
        </RouterLink>
      </Card>

      <!-- Preferences -->
      <div class="flex flex-col">
        <p class="mb-1 px-1 text-caption">
          {{ t('nav.preferences') }}
        </p>
        <Card padding="none" class="flex items-center justify-between gap-3 px-4 py-3">
          <LocaleSwitcher />
          <ThemeToggle />
        </Card>
      </div>

      <!-- Session -->
      <Button variant="destructive" class="w-full" @click="signOut">
        <LogOut class="size-4" />
        <span>{{ t('nav.logout') }}</span>
      </Button>
    </template>

    <AppFooter />
  </section>
</template>
