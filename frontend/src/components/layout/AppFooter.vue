<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { ArrowUpRight } from '@lucide/vue'

import { useAppConfig, useFeatureFlags } from '@/features/config/composables/useAppConfig'
import { APP_VERSION } from '@/constants/appVersion'
import { INTEGRATION_LOGOS } from '@/constants/integrationLogos'
import { SOCIAL_LINKS } from '@/constants/socialLinks'

const { t } = useI18n()
const { config } = useAppConfig()
const { isEnabled } = useFeatureFlags()

const REPOSITORY_URL = 'https://github.com/endurain-project/endurain'

const TRADEMARK_POLICY_URL = `${REPOSITORY_URL}/blob/master/TRADEMARK.md`

const startYear = 2023
const yearRange = computed(() => {
  const current = new Date().getFullYear()
  return current === startYear ? `${startYear}` : `${startYear} - ${current}`
})

const projectLinks = computed(() => [
  { key: 'website', label: t('footer.website'), href: 'https://endurain.com' },
  { key: 'documentation', label: t('footer.documentation'), href: 'https://docs.endurain.com' },
  { key: 'sourceCode', label: t('footer.sourceCode'), href: REPOSITORY_URL },
])

const linkClass =
  'inline-flex min-h-11 items-center gap-1.5 text-sm text-foreground hover:text-primary lg:min-h-8'
</script>

<template>
  <footer class="lg:border-t lg:border-border lg:bg-card">
    <div class="mx-auto flex w-full max-w-7xl flex-col gap-6 px-3 py-6 lg:py-8">
      <div class="grid grid-cols-2 gap-x-4 gap-y-6 lg:grid-cols-[2fr_1fr_1fr] lg:gap-8">
        <div class="col-span-2 flex flex-col items-start gap-2 lg:col-span-1">
          <span class="text-section-heading">{{ config.branding.appName }}</span>
          <p class="max-w-xs text-sm text-muted-foreground">
            {{ t('login.tagline1') }}<br />{{ t('login.tagline2') }}
          </p>
          <a
            :class="[
              'mt-1 inline-flex min-h-7 items-center rounded-badge bg-secondary px-3',
              'text-hint font-medium text-secondary-foreground hover:opacity-90',
            ]"
            :href="`${REPOSITORY_URL}/releases/tag/${APP_VERSION}`"
            target="_blank"
            rel="noopener noreferrer"
          >
            {{ t('footer.releaseNotes', { version: APP_VERSION }) }}
          </a>
        </div>

        <nav :aria-label="t('footer.project')" class="flex flex-col">
          <span class="mb-1 text-caption uppercase">{{ t('footer.project') }}</span>
          <a
            v-for="link in projectLinks"
            :key="link.key"
            :class="linkClass"
            :href="link.href"
            target="_blank"
            rel="noopener noreferrer"
          >
            {{ link.label }}
            <ArrowUpRight class="size-3.5 text-muted-foreground" aria-hidden="true" />
            <span class="sr-only">({{ t('footer.externalLink') }})</span>
          </a>
        </nav>

        <nav :aria-label="t('footer.community')" class="flex flex-col">
          <span class="mb-1 text-caption uppercase">{{ t('footer.community') }}</span>
          <a
            v-for="link in SOCIAL_LINKS"
            :key="link.key"
            :class="linkClass"
            :href="link.href"
            target="_blank"
            rel="noopener noreferrer"
            :aria-label="t(`footer.${link.key}`)"
          >
            {{ link.label }}
            <ArrowUpRight class="size-3.5 text-muted-foreground" aria-hidden="true" />
          </a>
        </nav>
      </div>

      <div
        class="flex flex-col-reverse gap-3 border-t border-border pt-4 lg:flex-row lg:items-center lg:justify-between"
      >
        <div class="flex flex-col gap-1 text-hint text-muted-foreground">
          <span>© {{ yearRange }} {{ config.branding.appName }}</span>
          <span>
            {{ t('footer.trademarkNotice') }}
            <a
              class="underline hover:text-foreground"
              :href="TRADEMARK_POLICY_URL"
              target="_blank"
              rel="noopener noreferrer"
            >
              {{ t('footer.trademarkPolicy') }}
            </a>
          </span>
        </div>
        <div
          v-if="isEnabled('strava') || isEnabled('garmin')"
          class="flex flex-wrap items-center gap-3"
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
        </div>
      </div>
    </div>
  </footer>
</template>
