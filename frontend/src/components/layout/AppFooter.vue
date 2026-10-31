<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { BookOpen, GitBranch } from '@lucide/vue'

import { useAppConfig, useFeatureFlags } from '@/features/config/composables/useAppConfig'
import { APP_VERSION } from '@/constants/appVersion'
import { INTEGRATION_LOGOS } from '@/constants/integrationLogos'
import { SOCIAL_LINKS } from '@/constants/socialLinks'

const { t } = useI18n()
const { config } = useAppConfig()
const { isEnabled } = useFeatureFlags()

const startYear = 2023
const yearRange = computed(() => {
  const current = new Date().getFullYear()
  return current === startYear ? `${startYear}` : `${startYear} - ${current}`
})
</script>

<template>
  <footer class="lg:border-t lg:border-border lg:bg-card">
    <div class="mx-auto flex w-full max-w-5xl flex-col items-center gap-3 px-3 py-6 text-center">
      <p
        class="flex flex-wrap items-center justify-center gap-x-2 gap-y-1 text-sm text-muted-foreground"
      >
        <span>© {{ yearRange }} {{ config.branding.appName }}</span>
        <span aria-hidden="true">•</span>
        <a
          class="inline-flex items-center hover:text-foreground"
          href="https://github.com/endurain-project"
          target="_blank"
          rel="noopener noreferrer"
          :aria-label="t('footer.repository')"
        >
          <GitBranch class="size-4" />
        </a>
        <span aria-hidden="true">•</span>
        <a
          class="inline-flex items-center hover:text-foreground"
          href="https://docs.endurain.com"
          target="_blank"
          rel="noopener noreferrer"
          :aria-label="t('footer.documentation')"
        >
          <BookOpen class="size-4" />
        </a>
        <template v-for="link in SOCIAL_LINKS" :key="link.key">
          <span aria-hidden="true">•</span>
          <a
            class="inline-flex items-center hover:text-foreground"
            :href="link.href"
            target="_blank"
            rel="noopener noreferrer"
            :aria-label="t(`footer.${link.key}`)"
          >
            <svg viewBox="0 0 24 24" fill="currentColor" class="size-4" aria-hidden="true">
              <path :d="link.path" />
            </svg>
          </a>
        </template>
        <span aria-hidden="true">•</span>
        <span>{{ APP_VERSION }}</span>
      </p>

      <p
        v-if="isEnabled('strava') || isEnabled('garmin')"
        class="flex flex-wrap items-center justify-center gap-3"
      >
        <img
          v-if="isEnabled('strava')"
          :src="INTEGRATION_LOGOS.strava"
          :alt="t('footer.compatibleStrava')"
          height="25"
          class="h-[25px] w-auto"
        />
        <img
          v-if="isEnabled('garmin')"
          :src="INTEGRATION_LOGOS.garmin"
          :alt="t('footer.worksGarmin')"
          height="25"
          class="h-[25px] w-auto"
        />
      </p>
    </div>
  </footer>
</template>
