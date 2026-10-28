<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { Pencil, Trash2 } from '@lucide/vue'

import type { FastingEntry, FastingStatus } from '@/features/health/types'

import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { INTEGRATION_LOGOS } from '@/constants/integrationLogos'
import { formatHoursMinutes } from '@/features/health/utils/healthFormat'
import { formatMediumDateTime } from '@/utils/datetime'

const props = defineProps<{
  /** The fasting session to render. */
  entry: FastingEntry
}>()
const emit = defineEmits<{ edit: [entry: FastingEntry]; delete: [entry: FastingEntry] }>()

const { t, locale } = useI18n()

/** Badge colour per fasting status. */
const STATUS_VARIANTS: Record<FastingStatus, 'default' | 'info' | 'warning' | 'outline'> = {
  completed: 'default',
  in_progress: 'info',
  broken: 'warning',
  cancelled: 'outline',
}

const statusVariant = computed(() =>
  props.entry.status ? STATUS_VARIANTS[props.entry.status] : 'outline',
)

/** Recorded length of the fast, shown in parentheses after the type. */
const durationLabel = computed(() =>
  props.entry.actualDurationSeconds != null
    ? formatHoursMinutes(props.entry.actualDurationSeconds, t)
    : null,
)

/** `start → end` window, or whichever bound is available. */
const rangeLabel = computed(() => {
  const start = props.entry.fastStartTime
    ? formatMediumDateTime(props.entry.fastStartTime, locale.value)
    : ''
  const end = props.entry.fastEndTime
    ? formatMediumDateTime(props.entry.fastEndTime, locale.value)
    : ''
  if (start && end) {
    return `${start} → ${end}`
  }
  return start || end || ''
})

const fromGarmin = computed(() => props.entry.source === 'garmin')
</script>

<template>
  <div class="px-4 py-3">
    <div class="flex items-start justify-between gap-3">
      <div class="flex min-w-0 flex-col gap-1">
        <div class="flex flex-wrap items-center gap-1.5">
          <p class="text-item-title">
            {{ entry.fastingType ?? '—' }}
            <span v-if="durationLabel" class="text-hint">({{ durationLabel }})</span>
          </p>
          <Badge v-if="entry.status" :variant="statusVariant">
            {{ t(`health.fasting.status.${entry.status}`) }}
          </Badge>
        </div>
        <p v-if="rangeLabel" class="text-hint">{{ rangeLabel }}</p>
        <p v-if="entry.notes" class="text-hint break-words whitespace-pre-line">
          {{ entry.notes }}
        </p>
      </div>
      <div class="flex shrink-0 items-center gap-1">
        <img
          v-if="fromGarmin"
          :src="INTEGRATION_LOGOS.garminApp"
          :alt="t('health.fasting.sourceGarmin')"
          :title="t('health.fasting.sourceGarmin')"
          class="size-4 shrink-0"
        />
        <Button
          variant="ghost"
          size="icon-sm"
          :aria-label="t('health.fasting.actions.edit')"
          @click="emit('edit', entry)"
        >
          <Pencil class="size-4" aria-hidden="true" />
        </Button>
        <Button
          variant="ghostDestructive"
          size="icon-sm"
          :aria-label="t('health.fasting.actions.delete')"
          @click="emit('delete', entry)"
        >
          <Trash2 class="size-4" aria-hidden="true" />
        </Button>
      </div>
    </div>
  </div>
</template>
