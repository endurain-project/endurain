<script setup lang="ts">
import { useI18n } from 'vue-i18n'

import type { HealthChartBucket } from '@/features/health/types'

import { Card } from '@/components/ui/card'

defineProps<{
  /** Heading shown beside the accent dot. */
  title: string
  /** Accent-dot colour (a resolved theme hex). */
  accentColor: string
  /** The span each bar aggregates; a caption explains any span longer than a day. */
  bucket?: HealthChartBucket
}>()

const { t } = useI18n()
</script>

<template>
  <Card class="flex min-w-0 flex-col gap-3">
    <div class="flex flex-col gap-1">
      <div class="flex items-center gap-2">
        <span
          class="size-2.5 rounded-full"
          :style="{ backgroundColor: accentColor }"
          aria-hidden="true"
        />
        <h3 class="text-card-heading">{{ title }}</h3>
      </div>
      <p v-if="bucket && bucket !== 'day'" class="text-meta" data-testid="chart-bucket-note">
        {{ t(`health.chartBucket.${bucket}`) }}
      </p>
    </div>
    <!-- The metric's canvas container is provided by the parent chart. -->
    <slot />
  </Card>
</template>
