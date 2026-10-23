<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'

import type { ChartInstance, ChartRenderOptions } from '@/composables/useChartProvider'
import type { StreamStat } from '@/features/activities/utils/streams'

import { Card } from '@/components/ui/card'
import { useChartProvider } from '@/composables/useChartProvider'
import { useRenderProvidersReady } from '@/providers'

const props = withDefaults(
  defineProps<{
    /** Localized chart title. */
    title: string
    /** Render options for the chart provider. */
    render: ChartRenderOptions
    /** Summary stats shown beneath the chart. */
    stats?: StreamStat[]
  }>(),
  { stats: () => [] },
)

const { t } = useI18n()

const ready = useRenderProvidersReady()
const container = ref<HTMLElement | null>(null)
let instance: ChartInstance | null = null

/** Legend swatch colour, taken from the (single) series. */
const swatchColor = computed(() => props.render.series[0]?.color ?? 'var(--color-brand)')

/**
 * Render options with series labels resolved through i18n. `buildStreamChart`
 * stores each metric's i18n *key* as the series label, so the tooltip would
 * otherwise read e.g. `activities.streams.heartRate`. Translating here keeps the
 * stream util pure; `t()` returns non-key strings unchanged, so an
 * already-localized label passes through.
 */
const chartRender = computed<ChartRenderOptions>(() => ({
  ...props.render,
  series: props.render.series.map((series) => ({ ...series, label: t(series.label) })),
}))

/** Mounts the chart once the provider is ready and the container exists. */
function mountChart(): void {
  if (instance || !container.value || !ready.value) {
    return
  }
  const { provider } = useChartProvider()
  instance = provider.mount(container.value, chartRender.value)
}

onMounted(mountChart)
watch(ready, mountChart)
watch(chartRender, (render) => {
  if (!instance) {
    mountChart()
    return
  }
  instance.update(render)
})

onBeforeUnmount(() => {
  instance?.destroy()
  instance = null
})
</script>

<template>
  <!-- min-w-0 lets the chart shrink inside the grid; without it the canvas
       forces the column wider than the viewport on mobile. -->
  <Card class="flex min-w-0 flex-col gap-3">
    <div class="flex items-center gap-2">
      <span
        class="size-2.5 rounded-full"
        :style="{ backgroundColor: swatchColor }"
        aria-hidden="true"
      />
      <h3 class="text-card-heading">{{ title }}</h3>
    </div>
    <div ref="container" class="relative h-56 w-full min-w-0" />
    <dl v-if="props.stats.length > 0" class="flex flex-wrap gap-x-6 gap-y-2">
      <div v-for="stat in props.stats" :key="stat.labelKey">
        <dt class="text-caption">{{ t(stat.labelKey) }}</dt>
        <dd class="text-item-title">
          {{ stat.value
          }}<span v-if="stat.unit" class="ms-1 text-hint font-normal">{{ t(stat.unit) }}</span>
        </dd>
      </div>
    </dl>
  </Card>
</template>
