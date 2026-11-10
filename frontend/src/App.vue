<script setup lang="ts">
import { computed } from 'vue'
import { RouterView, useRoute } from 'vue-router'

import AppNavbar from '@/components/layout/AppNavbar.vue'
import AppBottomNav from '@/components/layout/AppBottomNav.vue'
import AppFooter from '@/components/layout/AppFooter.vue'
import ErrorBoundary from '@/components/layout/ErrorBoundary.vue'
import ToastHost from '@/components/layout/ToastHost.vue'
import { Card } from '@/components/ui/card'
import SessionRestoreErrorOverlay from '@/features/auth/components/SessionRestoreErrorOverlay.vue'
import { useAuthStore } from '@/features/auth/stores/auth'
import ConfigErrorOverlay from '@/features/config/components/ConfigErrorOverlay.vue'
import { useAppConfig } from '@/features/config/composables/useAppConfig'

const route = useRoute()
const auth = useAuthStore()

// Set at boot when the backend host is unreachable (misconfigured
// ENDURAIN_HOST); when set, nothing else can work so we block the whole shell.
const { configError } = useAppConfig()

// Auth screens (login/signup) render bare — no navbar, footer, or bottom nav.
const showChrome = computed(() => !route.meta.bare)
// Wrap content views in the shared card container, mirroring v1. Bare screens
// (login) and cardless views (menu) supply their own surfaces and opt out.
const showCard = computed(() => showChrome.value && !route.meta.cardless)
</script>

<template>
  <ConfigErrorOverlay v-if="configError" />
  <!-- The server could not be asked about the session, so signed-in state is unknown: offer a retry. -->
  <SessionRestoreErrorOverlay v-else-if="auth.restoreFailed" />
  <div v-else class="flex min-h-svh flex-col bg-background text-foreground">
    <AppNavbar v-if="showChrome" />
    <main class="flex flex-1 flex-col">
      <div
        class="mx-auto w-full max-w-7xl px-3 py-3 sm:px-3 sm:py-3"
        :class="{ 'my-auto': !showChrome }"
      >
        <ErrorBoundary>
          <Card v-if="showCard" padding="lg">
            <RouterView />
          </Card>
          <RouterView v-else />
        </ErrorBoundary>
      </div>
    </main>
    <!-- Footer on the desktop shell only; on mobile it lives in the menu view. -->
    <AppFooter v-if="showChrome" class="hidden lg:block" />
    <AppBottomNav v-if="showChrome" />
    <ToastHost :below-navbar="showChrome" />
  </div>
</template>
