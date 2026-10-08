<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import { RouterView } from 'vue-router'

import { Alert } from '@/components/ui/alert'
import SettingsNav from '@/features/settings/components/SettingsNav.vue'
import { useUpdateCheck } from '@/features/core/composables/useUpdateCheck'

/**
 * Settings shell. Renders the page heading and a two-column layout — the zone
 * sidebar beside the active zone (a nested child route) — mirroring the gears
 * list shell. Below `lg` the sidebar collapses to the top of the flow so the
 * same content appears at every breakpoint.
 */
const { t } = useI18n()
const { updateAvailable, latestVersion } = useUpdateCheck()
</script>

<template>
  <section class="flex flex-col gap-3">
    <div class="grid gap-3 lg:grid-cols-[16rem_minmax(0,1fr)] lg:items-start">
      <aside class="flex flex-col gap-3 lg:sticky lg:top-6">
        <header class="flex flex-col gap-1">
          <h1 class="text-page-title">{{ t('settings.title') }}</h1>
          <p class="text-body">{{ t('settings.subtitle') }}</p>
        </header>

        <Alert v-if="updateAvailable" kind="warning">
          <p class="font-medium">
            {{
              latestVersion
                ? t('nav.updateAvailableTitle', { version: latestVersion })
                : t('nav.updateAvailable')
            }}
          </p>
          <a
            href="https://github.com/endurain-project/endurain/releases"
            target="_blank"
            rel="noopener noreferrer"
            class="mt-0.5 block text-meta underline underline-offset-2 opacity-80 hover:opacity-100"
          >
            {{ t('nav.updateViewRelease') }}
          </a>
        </Alert>

        <SettingsNav />
      </aside>

      <RouterView />
    </div>
  </section>
</template>
