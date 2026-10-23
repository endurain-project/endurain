<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { LocateFixed } from '@lucide/vue'

import type { GeoPoint, MapInstance } from '@/composables/useMapProvider'

import { useMapProvider } from '@/composables/useMapProvider'
import { useRenderProvidersReady } from '@/providers'

const props = withDefaults(
  defineProps<{
    /** Ordered GPS coordinates forming the route polyline. */
    points: GeoPoint[]
    /** Whether the map responds to pan/zoom. */
    interactive?: boolean
    /** Point on the route that follows the chart cursor. `null` hides it. */
    cursor?: GeoPoint | null
    /** Reports hover along the route so the charts can follow. */
    follow?: boolean
  }>(),
  { interactive: true, cursor: null, follow: false },
)

const emit = defineEmits<{
  trackHover: [fraction: number | null]
}>()

const ready = useRenderProvidersReady()
const container = ref<HTMLElement | null>(null)
let instance: MapInstance | null = null

/** Resolves the start/finish emphasis points from the track ends. */
function endpoints(points: GeoPoint[]): { start?: GeoPoint; finish?: GeoPoint } {
  const first = points[0]
  const last = points[points.length - 1]
  return first && last ? { start: first, finish: last } : {}
}

/** Mounts the map once the provider is ready and the container exists. */
function mountMap(): void {
  if (instance || !container.value || !ready.value || props.points.length === 0) {
    return
  }
  const { provider } = useMapProvider()
  instance = provider.mount(container.value, {
    track: { points: props.points, ...endpoints(props.points) },
    interactive: props.interactive,
  })
  syncCursor()
}

/** Moves the route marker and listens for hover without redrawing the line. */
function syncCursor(): void {
  instance?.setCursor(props.cursor ?? null)
  instance?.setTrackHover(props.follow ? (fraction) => emit('trackHover', fraction) : null)
}

/** Re-fits the map to the whole track after the user has panned or zoomed. */
function recenter(): void {
  instance?.recenter()
}

onMounted(mountMap)
watch(ready, mountMap)
watch(() => [props.cursor, props.follow] as const, syncCursor)
watch(
  () => props.points,
  (points) => {
    if (!instance) {
      mountMap()
      return
    }
    instance.update({
      track: { points, ...endpoints(points) },
      interactive: props.interactive,
    })
  },
)

onBeforeUnmount(() => {
  instance?.destroy()
  instance = null
})
</script>

<template>
  <!-- Fills its parent, which controls the height (e.g. a gallery slide).
       `isolate` creates a stacking context so Leaflet's internal panes and
       controls (z-index up to 1000) stay contained and never paint over the
       sticky navbar (z-40) or bottom nav while scrolling. -->
  <div class="relative isolate size-full overflow-hidden bg-muted">
    <div ref="container" class="size-full" role="img" :aria-label="$t('activities.map.label')" />
    <!-- z above Leaflet's controls (z-1000) so it stays clickable. -->
    <button
      v-if="interactive && points.length > 0"
      type="button"
      class="absolute top-3 right-3 z-[1100] flex size-9 items-center justify-center rounded-full bg-card/80 text-foreground backdrop-blur transition-colors hover:bg-card"
      :aria-label="$t('activities.map.recenter')"
      :title="$t('activities.map.recenter')"
      @click="recenter"
    >
      <LocateFixed class="size-4" />
    </button>
  </div>
</template>
