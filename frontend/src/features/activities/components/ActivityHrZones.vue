<script setup lang="ts">
import { useI18n } from 'vue-i18n'

import type { HrZoneBucket } from '@/features/activities/types'

import { formatHmsDuration } from '@/features/activities/utils/format'
import { hrZoneColor } from '@/features/activities/utils/hrZones'

defineProps<{
  /** Ordered HR zone buckets (zones 1–5). */
  zones: HrZoneBucket[]
}>()

const { t } = useI18n()

/** Clamps a percentage to the 0–100 range for the bar width. */
function barWidth(percent: number): string {
  return `${Math.min(100, Math.max(0, percent))}%`
}
</script>

<template>
  <div class="flex flex-col gap-2.5">
    <div v-for="zone in zones" :key="zone.zone" class="flex items-center gap-3">
      <div class="w-24 shrink-0">
        <p class="text-meta font-medium text-foreground">
          {{ t('activities.hrZones.zone') }} {{ zone.zone }}
        </p>
        <p v-if="zone.hrRange" class="text-caption">{{ zone.hrRange }}</p>
      </div>
      <div
        class="h-2.5 flex-1 overflow-hidden rounded-full bg-muted"
        role="progressbar"
        :aria-valuenow="Math.round(zone.percent)"
        aria-valuemin="0"
        aria-valuemax="100"
      >
        <div
          class="h-full rounded-full"
          :style="{ width: barWidth(zone.percent), backgroundColor: hrZoneColor(zone.zone) }"
        />
      </div>
      <div class="w-20 shrink-0 text-right">
        <p class="text-meta font-medium text-foreground">{{ Math.round(zone.percent) }}%</p>
        <p v-if="zone.timeSeconds > 0" class="text-caption">
          {{ formatHmsDuration(zone.timeSeconds) }}
        </p>
      </div>
    </div>
  </div>
</template>
