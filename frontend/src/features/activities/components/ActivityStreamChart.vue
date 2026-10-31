<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'

import type { ChartInstance, ChartRenderOptions } from '@/composables/useChartProvider'
import type { StreamStat } from '@/features/activities/utils/streams'

import { Card } from '@/components/ui/card'
import { useChartProvider } from '@/composables/useChartProvider'
import { indexAtFraction } from '@/features/activities/utils/scrub'
import { useRenderProvidersReady } from '@/providers'

const props = withDefaults(
  defineProps<{
    /** Localized chart title. */
    title: string
    /** Render options for the chart provider. */
    render: ChartRenderOptions
    /** Summary stats shown beneath the chart. */
    stats?: StreamStat[]
    /** Shared position along the activity, from 0 to 1. `null` hides the cursor. */
    cursorFraction?: number | null
  }>(),
  { stats: () => [], cursorFraction: null },
)

const emit = defineEmits<{
  /** Pointer position along this chart, or `null` when it leaves the plot. */
  scrub: [fraction: number | null]
}>()

const { t } = useI18n()

const ready = useRenderProvidersReady()
const plot = ref<HTMLElement | null>(null)
const container = ref<HTMLElement | null>(null)
const layoutTick = ref(0)
let instance: ChartInstance | null = null
let resizeObserver: ResizeObserver | null = null

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

/** Shared cursor drawn over the plot. The chart itself is not redrawn. */
const cursor = computed(() => {
  void layoutTick.value
  const fraction = props.cursorFraction
  const series = chartRender.value.series[0]
  if (fraction == null || !instance || !series || series.data.length === 0) {
    return null
  }
  const geometry = instance.cursorGeometry(fraction)
  if (!geometry) {
    return null
  }
  const index = indexAtFraction(series.data.length, fraction)
  const value = series.data[index]
  if (value === undefined || Number.isNaN(value)) {
    return null
  }
  const formatted = chartRender.value.valueFormat?.(value) ?? String(value)
  const rawLabel = chartRender.value.labels?.[index]
  const xLabel = rawLabel
    ? chartRender.value.xUnit
      ? `${rawLabel} ${chartRender.value.xUnit}`
      : String(rawLabel)
    : ''
  return {
    ...geometry,
    text: xLabel ? `${xLabel} · ${formatted}` : formatted,
    alignEnd: fraction > 0.72,
  }
})

/** Reports this chart's position so the other charts and the map can follow. */
function onPointerMove(event: PointerEvent): void {
  emit('scrub', instance?.fractionAt(event.clientX) ?? null)
}

onMounted(() => {
  mountChart()
  if (!plot.value) {
    return
  }
  resizeObserver = new ResizeObserver(() => {
    layoutTick.value += 1
  })
  resizeObserver.observe(plot.value)
})
watch(ready, mountChart)
watch(chartRender, (render) => {
  if (!instance) {
    mountChart()
    return
  }
  instance.update(render)
  layoutTick.value += 1
})

onBeforeUnmount(() => {
  resizeObserver?.disconnect()
  resizeObserver = null
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
    <div
      ref="plot"
      class="relative h-56 w-full min-w-0 cursor-crosshair"
      @pointermove="onPointerMove"
    >
      <div ref="container" class="size-full" />
      <div
        v-if="cursor"
        class="pointer-events-none absolute w-px bg-foreground/70"
        :style="{ left: `${cursor.left}px`, top: `${cursor.top}px`, height: `${cursor.height}px` }"
      >
        <div
          class="absolute top-1 whitespace-nowrap rounded-input border border-border bg-popover px-2 py-1 text-micro text-popover-foreground shadow-sm"
          :class="cursor.alignEnd ? 'right-2' : 'left-2'"
        >
          {{ cursor.text }}
        </div>
      </div>
    </div>
    <dl v-if="props.stats.length > 0" class="flex flex-wrap gap-x-6 gap-y-2">
      <div v-for="stat in props.stats" :key="stat.labelKey">
        <dt class="text-caption">{{ t(stat.labelKey) }}</dt>
        <dd class="text-item-title">
          {{ stat.value
          }}<span v-if="stat.unit" class="ms-1 text-hint font-normal">{{ stat.unit }}</span>
        </dd>
      </div>
    </dl>
  </Card>
</template>
