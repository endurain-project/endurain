<script setup lang="ts">
import { computed, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { ChevronDown, Pencil, Trash2 } from '@lucide/vue'

import type { Schemas } from '@/types'
import type { WeightEntry } from '@/features/health/types'

import { Button } from '@/components/ui/button'
import { INTEGRATION_LOGOS } from '@/constants/integrationLogos'
import {
  formatBmi,
  formatBodyMass,
  formatHealthEntryDate,
  formatWeight,
} from '@/features/health/utils/healthFormat'

const props = defineProps<{
  /** The weight entry to render. */
  entry: WeightEntry
  /** The measurement system used to present body mass (kg or lbs). */
  weightUnits: Schemas['Units']
}>()
const emit = defineEmits<{ edit: [entry: WeightEntry]; delete: [entry: WeightEntry] }>()

const { t, locale } = useI18n()

const expanded = ref(false)

/** Whether any optional body-composition metric is present to reveal. */
const hasDetails = computed(
  () =>
    props.entry.bmi !== null ||
    props.entry.bodyFatPct !== null ||
    props.entry.bodyWaterPct !== null ||
    props.entry.boneMassKg !== null ||
    props.entry.muscleMassKg !== null,
)

/** Primary weight string, or an em dash when the entry carries no weight. */
const weightLabel = computed(() =>
  props.entry.weightKg === null ? '—' : formatWeight(props.entry.weightKg, props.weightUnits),
)

const dateLabel = computed(() => formatHealthEntryDate(props.entry.date, locale.value))
const fromGarmin = computed(() => props.entry.source === 'garmin')
</script>

<template>
  <div class="px-4 py-3">
    <div class="flex items-center justify-between gap-3">
      <div class="flex min-w-0 items-center gap-2">
        <p class="text-item-title">{{ weightLabel }}</p>
      </div>
      <div class="flex shrink-0 items-center gap-1">
        <img
          v-if="fromGarmin"
          :src="INTEGRATION_LOGOS.garminApp"
          :alt="t('health.weight.sourceGarmin')"
          :title="t('health.weight.sourceGarmin')"
          class="size-4 shrink-0"
        />
        <Button
          v-if="hasDetails"
          variant="ghost"
          size="icon-sm"
          :aria-label="t('health.weight.toggleDetails')"
          :aria-expanded="expanded"
          @click="expanded = !expanded"
        >
          <ChevronDown
            class="size-4 transition-transform"
            :class="{ 'rotate-180': expanded }"
            aria-hidden="true"
          />
        </Button>
        <Button
          variant="ghost"
          size="icon-sm"
          :aria-label="t('health.weight.actions.edit')"
          @click="emit('edit', entry)"
        >
          <Pencil class="size-4" aria-hidden="true" />
        </Button>
        <Button
          variant="ghostDestructive"
          size="icon-sm"
          :aria-label="t('health.weight.actions.delete')"
          @click="emit('delete', entry)"
        >
          <Trash2 class="size-4" aria-hidden="true" />
        </Button>
      </div>
    </div>
    <p class="text-hint">{{ dateLabel }}</p>
    <dl v-if="hasDetails && expanded" class="mt-2 grid grid-cols-2 gap-x-4 gap-y-1 sm:grid-cols-3">
      <div v-if="entry.bmi !== null">
        <dt class="text-caption">{{ t('health.weight.detail.bmi') }}</dt>
        <dd class="text-hint">{{ formatBmi(entry.bmi) }}</dd>
      </div>
      <div v-if="entry.bodyFatPct !== null">
        <dt class="text-caption">{{ t('health.weight.detail.bodyFat') }}</dt>
        <dd class="text-hint">{{ entry.bodyFatPct.toFixed(1) }}%</dd>
      </div>
      <div v-if="entry.bodyWaterPct !== null">
        <dt class="text-caption">{{ t('health.weight.detail.bodyWater') }}</dt>
        <dd class="text-hint">{{ entry.bodyWaterPct.toFixed(1) }}%</dd>
      </div>
      <div v-if="entry.boneMassKg !== null">
        <dt class="text-caption">{{ t('health.weight.detail.boneMass') }}</dt>
        <dd class="text-hint">{{ formatBodyMass(entry.boneMassKg, weightUnits) }}</dd>
      </div>
      <div v-if="entry.muscleMassKg !== null">
        <dt class="text-caption">{{ t('health.weight.detail.muscleMass') }}</dt>
        <dd class="text-hint">{{ formatBodyMass(entry.muscleMassKg, weightUnits) }}</dd>
      </div>
    </dl>
  </div>
</template>
