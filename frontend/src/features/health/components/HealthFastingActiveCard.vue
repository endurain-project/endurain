<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { Ban, Check, Clock, Square } from '@lucide/vue'

import type { FastingEntry, FastingStatus } from '@/features/health/types'

import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
import { formatElapsedClock, formatHoursMinutes } from '@/features/health/utils/healthFormat'
import { formatMediumDateTime } from '@/utils/datetime'

const props = defineProps<{
  /** The in-progress fasting session to display. */
  entry: FastingEntry
  /** Whether a complete/break/cancel mutation is currently in flight. */
  completing: boolean
}>()

const emit = defineEmits<{ complete: [status: FastingStatus] }>()

const { t, locale } = useI18n()

// Ticking clock: a 1s interval drives `now` so the elapsed time updates live.
const now = ref(Date.now())
let timer: ReturnType<typeof setInterval> | undefined

onMounted(() => {
  timer = setInterval(() => {
    now.value = Date.now()
  }, 1000)
})
onBeforeUnmount(() => {
  if (timer) {
    clearInterval(timer)
  }
})

/** Epoch milliseconds of the fast's start, or `null` when unparseable. */
const startMs = computed(() => {
  if (!props.entry.fastStartTime) {
    return null
  }
  const ms = new Date(props.entry.fastStartTime).getTime()
  return Number.isNaN(ms) ? null : ms
})

/** Seconds elapsed since the fast began, never negative. */
const elapsedSeconds = computed(() =>
  startMs.value === null ? 0 : Math.max(0, Math.floor((now.value - startMs.value) / 1000)),
)

const clock = computed(() => formatElapsedClock(elapsedSeconds.value))

const hasTarget = computed(
  () => props.entry.targetDurationSeconds !== null && props.entry.targetDurationSeconds > 0,
)

/** Progress toward the target, clamped to 0–100; zero when no target is set. */
const progressPct = computed(() => {
  if (!hasTarget.value) {
    return 0
  }
  const target = props.entry.targetDurationSeconds as number
  return Math.min(100, Math.round((elapsedSeconds.value / target) * 100))
})

// Completing is gated on reaching the target (matching v1); with no target set
// it is always allowed so the fast can never get stuck.
const canComplete = computed(
  () => !props.completing && (!hasTarget.value || progressPct.value >= 100),
)

const startedLabel = computed(() =>
  props.entry.fastStartTime ? formatMediumDateTime(props.entry.fastStartTime, locale.value) : '',
)
const targetLabel = computed(() =>
  hasTarget.value ? formatHoursMinutes(props.entry.targetDurationSeconds as number, t) : null,
)
</script>

<template>
  <Card class="flex flex-col gap-3">
    <div class="flex items-start justify-between gap-2">
      <div class="flex items-center gap-2">
        <Clock class="size-4 text-brand-mid" aria-hidden="true" />
        <h2 class="text-section-heading">{{ t('health.fasting.active.title') }}</h2>
      </div>
      <Badge v-if="entry.fastingType" variant="info">{{ entry.fastingType }}</Badge>
    </div>

    <div class="flex flex-col items-center gap-1 py-2">
      <p class="text-display font-medium tabular-nums tracking-tight text-foreground">
        {{ clock }}
      </p>
      <p v-if="startedLabel" class="text-hint">
        {{ t('health.fasting.active.started') }}: {{ startedLabel }}
      </p>
    </div>

    <div v-if="hasTarget" class="flex flex-col gap-1">
      <div class="flex items-center justify-between text-hint">
        <span>{{ t('health.fasting.active.target') }}: {{ targetLabel }}</span>
        <span class="tabular-nums">{{ progressPct }}%</span>
      </div>
      <div
        class="h-2 overflow-hidden rounded-full bg-muted"
        role="progressbar"
        :aria-valuenow="progressPct"
        aria-valuemin="0"
        aria-valuemax="100"
      >
        <div
          class="h-full rounded-full bg-brand-mid transition-[width]"
          :style="{ width: `${progressPct}%` }"
        />
      </div>
    </div>

    <div class="flex flex-wrap gap-2">
      <Button :disabled="!canComplete" @click="emit('complete', 'completed')">
        <Check class="size-4" aria-hidden="true" />
        {{ t('health.fasting.active.complete') }}
      </Button>
      <Button variant="outline" :disabled="completing" @click="emit('complete', 'broken')">
        <Square class="size-4" aria-hidden="true" />
        {{ t('health.fasting.active.break') }}
      </Button>
      <Button
        variant="ghostDestructive"
        :disabled="completing"
        @click="emit('complete', 'cancelled')"
      >
        <Ban class="size-4" aria-hidden="true" />
        {{ t('health.fasting.active.cancel') }}
      </Button>
    </div>

    <p v-if="hasTarget && progressPct < 100" class="text-hint">
      {{ t('health.fasting.active.completeHint') }}
    </p>
  </Card>
</template>
