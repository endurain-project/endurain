<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'

import type { Activity } from '@/features/activities/types'
import type { Units } from '@/features/activities/utils/format'
import type { MetricVisibility } from '@/features/activities/utils/metrics'

import { MetricPill } from '@/components/ui/metric-pill'
import { useUnitFormat } from '@/composables/useUnitFormat'
import { buildActivityMetrics } from '@/features/activities/utils/metrics'

const props = defineProps<{
  activity: Activity
  units: Units
  visibility: MetricVisibility
}>()

const { t } = useI18n()
const { unitLabel } = useUnitFormat()

const tiles = computed(() => buildActivityMetrics(props.activity, props.units, props.visibility))
</script>

<template>
  <div class="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-3">
    <MetricPill
      v-for="tile in tiles"
      :key="tile.key"
      :label="t(tile.labelKey)"
      :value="tile.value"
      :unit="tile.unit ? unitLabel(tile.unit) : undefined"
      :accent="tile.accent"
      class=""
    />
  </div>
</template>
