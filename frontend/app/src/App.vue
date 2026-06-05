<script setup>
import { computed } from 'vue'
import { RouterView } from 'vue-router'
import NavbarComponent from './components/Navbar/NavbarComponent.vue'
import NavbarBottomMobileComponent from './components/Navbar/NavbarBottomMobileComponent.vue'
import FooterComponent from './components/FooterComponent.vue'
import { Notivue, Notification, NotivueSwipe, NotificationProgress, pastelTheme } from 'notivue'
import { useServerSettingsStore } from '@/stores/serverSettingsStore'

const serverSettingsStore = useServerSettingsStore()
const configError = computed(() => serverSettingsStore.configError)
const configuredHost = window.env?.ENDURAIN_HOST || ''
</script>

<template>
  <Notivue v-slot="item">
    <NotivueSwipe :item="item">
      <Notification :item="item" :theme="pastelTheme">
        <NotificationProgress :item="item" />
      </Notification>
    </NotivueSwipe>
  </Notivue>

  <!-- Configuration error overlay -->
  <div
    v-if="configError"
    class="d-flex flex-column min-vh-100 justify-content-center align-items-center p-4 bg-body-tertiary"
  >
    <div class="card shadow-sm" style="max-width: 600px; width: 100%">
      <div class="card-body text-center p-4">
        <font-awesome-icon
          :icon="['fas', 'triangle-exclamation']"
          class="text-warning mb-3"
          style="font-size: 2.5rem"
        />
        <h2 class="mb-3">{{ $t('generalItems.configErrorTitle') }}</h2>
        <p class="text-muted mb-3">{{ $t('generalItems.configErrorMessage') }}</p>
        <div class="alert alert-secondary text-start font-monospace small mb-3">
          <strong>ENDURAIN_HOST</strong>: {{ configuredHost || $t('generalItems.configErrorNotSet') }}
        </div>
        <p class="text-muted small">{{ $t('generalItems.configErrorHelp') }}</p>
      </div>
    </div>
  </div>

  <!-- Normal app layout -->
  <div v-else class="d-flex flex-column min-vh-100">
    <!-- Top Navbar with safe-area padding -->
    <div class="bg-body-tertiary shadow-sm safe-area-top">
      <NavbarComponent class="container safe-area-container" />
    </div>

    <!-- Main content -->
    <main class="container safe-area-container py-4 flex-grow-1">
      <RouterView />
    </main>

    <!-- Desktop Footer -->
    <FooterComponent class="d-none d-lg-block shadow-sm" />

    <!-- Bottom Mobile Navbar with safe-area padding -->
    <NavbarBottomMobileComponent
      class="d-lg-none d-block sticky-bottom shadow-sm safe-area-bottom"
    />
  </div>
</template>

<style>
/* Top navbar safe area */
.safe-area-top {
  padding-top: constant(safe-area-inset-top);
  padding-top: env(safe-area-inset-top);
}

/* Bottom mobile navbar safe area */
.safe-area-bottom {
  padding-bottom: constant(safe-area-inset-bottom);
  padding-bottom: env(safe-area-inset-bottom);
  background-clip: padding-box;
}

/* Main container safe areas */
.safe-area-container {
  padding-left: max(0.75rem, constant(safe-area-inset-left));
  padding-left: max(0.75rem, env(safe-area-inset-left));
  padding-right: max(0.75rem, constant(safe-area-inset-right));
  padding-right: max(0.75rem, env(safe-area-inset-right));
}
</style>
