<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { RouterLink } from 'vue-router'

import type { Gear } from '@/features/gears/types'

import GearTypeIcon from '@/features/gears/components/GearTypeIcon.vue'
import GearBadges from '@/features/gears/components/GearBadges.vue'

/**
 * One gear row in the search results: type icon, nickname, and creation date,
 * linking to the gear detail view. Status and provenance badges (inactive, plus
 * Strava/Garmin links) are rendered via the shared `GearBadges` component.
 */
const props = defineProps<{ gear: Gear }>()

const { locale } = useI18n()

/** The localized creation date, or `null` when the gear has no/invalid date. */
const dateLabel = computed(() => {
  if (!props.gear.createdAt) {
    return null
  }
  const date = new Date(props.gear.createdAt)
  if (Number.isNaN(date.getTime())) {
    return null
  }
  return new Intl.DateTimeFormat(locale.value, { dateStyle: 'medium', timeZone: 'UTC' }).format(
    date,
  )
})
</script>

<template>
  <RouterLink
    :to="{ name: 'gear', params: { id: gear.id } }"
    class="flex items-center gap-3 px-4 py-3 transition-colors hover:bg-muted/50"
  >
    <span
      class="flex size-10 shrink-0 items-center justify-center rounded-full bg-muted text-muted-foreground"
    >
      <GearTypeIcon :type="gear.gearType" class="size-7" />
    </span>
    <div class="min-w-0 flex-1">
      <p class="truncate font-medium text-foreground">{{ gear.nickname }}</p>
      <p v-if="dateLabel" class="truncate text-hint">{{ dateLabel }}</p>
    </div>
    <GearBadges :gear="gear" class="shrink-0" />
  </RouterLink>
</template>
