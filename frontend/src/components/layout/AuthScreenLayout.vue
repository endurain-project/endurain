<script setup lang="ts">
import { useI18n } from 'vue-i18n'

import { APP_VERSION } from '@/constants/appVersion'

/**
 * Presentational split-card shell shared by the login and sign-up screens: a
 * brand photo column (with a legibility scrim and taglines) on large screens,
 * and a centered content column that renders the default slot. Screens own
 * their own form/markup; this component only owns the surrounding chrome.
 */
defineProps<{
  /** Source URL for the brand photo shown in the left column. */
  imageUrl: string
  /** Accessible alt text for the brand photo. */
  imageAlt: string
}>()

const { t } = useI18n()
</script>

<template>
  <section class="mx-auto w-full max-w-7xl">
    <div
      class="grid overflow-hidden rounded-card border border-border bg-card p-3 lg:grid-cols-2 lg:gap-3"
    >
      <!-- Brand photo, hidden on small screens where the form shows its own
           taglines/subtitle. The scrim keeps the overlay legible over any
           user-supplied photo. -->
      <div class="relative hidden overflow-hidden rounded-input lg:block">
        <img
          width="640"
          height="640"
          :src="imageUrl"
          :alt="imageAlt"
          class="h-full min-h-[520px] w-full object-cover"
        />
        <div
          class="absolute inset-0 bg-gradient-to-b from-black/40 via-transparent to-black/75"
        ></div>
        <div class="absolute inset-x-0 bottom-0 p-6 text-card-heading leading-snug text-white">
          <p>{{ t('login.tagline1') }}</p>
          <p>{{ t('login.tagline2') }}</p>
        </div>
      </div>

      <div class="flex min-h-[520px] flex-col justify-center px-2 py-6 sm:px-6 lg:px-8">
        <slot />
        <p class="mt-6 text-center text-meta text-muted-foreground">{{ APP_VERSION }}</p>
      </div>
    </div>
  </section>
</template>
