<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { Pencil, Trash2 } from '@lucide/vue'

import type { PoopColor, PoopEntry } from '@/features/health/types'
import { bristolNumber } from '@/features/health/utils/bristol'

import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { formatMediumDateTime } from '@/utils/datetime'

const props = defineProps<{
  /** The poop entry to render. */
  entry: PoopEntry
}>()
const emit = defineEmits<{ edit: [entry: PoopEntry]; delete: [entry: PoopEntry] }>()

const { t, locale } = useI18n()

/** Swatch colour per stool colour, used for the small dot in the colour badge. */
const COLOR_SWATCHES: Record<PoopColor, string> = {
  brown: '#8b4513',
  dark_brown: '#5c3317',
  light_brown: '#c8956c',
  yellow: '#f5c518',
  green: '#4caf50',
  black: '#222222',
  red: '#d32f2f',
  white: '#e0e0e0',
}

const dateTimeLabel = computed(() =>
  props.entry.dateTime ? formatMediumDateTime(props.entry.dateTime, locale.value) : '',
)
const swatch = computed(() => (props.entry.color ? COLOR_SWATCHES[props.entry.color] : undefined))
const hasDetails = computed(() => props.entry.bristolType !== null || props.entry.color !== null)
</script>

<template>
  <div class="px-4 py-3">
    <div class="flex items-start justify-between gap-3">
      <div class="flex min-w-0 flex-col gap-1">
        <div class="flex flex-wrap items-center gap-1.5">
          <Badge v-if="entry.bristolType !== null" variant="secondary">
            {{ t('health.poop.list.bristolBadge', { type: bristolNumber(entry.bristolType) }) }}
          </Badge>
          <Badge v-if="entry.color" variant="outline" class="gap-1">
            <span
              class="size-2 rounded-full border border-border"
              :style="{ backgroundColor: swatch }"
              aria-hidden="true"
            />
            {{ t(`health.poop.form.colors.${entry.color}`) }}
          </Badge>
          <span v-if="!hasDetails" class="text-item-title">{{
            t('health.poop.list.noDetails')
          }}</span>
        </div>
        <p class="text-hint">{{ dateTimeLabel }}</p>
        <p v-if="entry.notes" class="text-hint break-words whitespace-pre-line">
          {{ entry.notes }}
        </p>
      </div>
      <div class="flex shrink-0 items-center gap-1">
        <Button
          variant="ghost"
          size="icon-sm"
          :aria-label="t('health.poop.actions.edit')"
          @click="emit('edit', entry)"
        >
          <Pencil class="size-4" aria-hidden="true" />
        </Button>
        <Button
          variant="ghostDestructive"
          size="icon-sm"
          :aria-label="t('health.poop.actions.delete')"
          @click="emit('delete', entry)"
        >
          <Trash2 class="size-4" aria-hidden="true" />
        </Button>
      </div>
    </div>
  </div>
</template>
