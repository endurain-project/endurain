<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { Pencil, Trash2 } from '@lucide/vue'

import type { Gear } from '@/features/gears/types'

import GearTypeIcon from '@/features/gears/components/GearTypeIcon.vue'
import GearBadges from '@/features/gears/components/GearBadges.vue'
import { Button } from '@/components/ui/button'
import { Spinner } from '@/components/ui/spinner'
import { presentGearType } from '@/features/gears/utils/gearType'

const props = defineProps<{
  gear: Gear
  /** Whether the gear is being deleted, which disables its actions. */
  deleting?: boolean
}>()
const emit = defineEmits<{ edit: [gear: Gear]; delete: [gear: Gear] }>()

const { t } = useI18n()

const typeLabel = computed(() => t(presentGearType(props.gear.gearType).labelKey))
</script>

<template>
  <div class="flex items-center justify-between gap-3 px-4 py-3">
    <div class="flex min-w-0 items-center gap-3">
      <span
        class="flex size-10 shrink-0 items-center justify-center rounded-full bg-muted text-muted-foreground"
      >
        <GearTypeIcon :type="gear.gearType" class="size-7" />
      </span>
      <div class="min-w-0">
        <RouterLink
          :to="{ name: 'gear', params: { id: gear.id } }"
          class="block truncate font-medium text-foreground hover:underline"
        >
          {{ gear.nickname }}
        </RouterLink>
        <div class="flex items-center gap-2">
          <p class="truncate text-hint">{{ typeLabel }}</p>
          <GearBadges :gear="gear" />
          <span v-if="deleting" class="inline-flex items-center gap-1 text-hint">
            <Spinner size="sm" />
            {{ t('gears.delete.deleting') }}
          </span>
        </div>
      </div>
    </div>
    <div class="flex shrink-0 items-center gap-1">
      <Button
        variant="ghost"
        size="icon-sm"
        :aria-label="t('gears.actions.edit')"
        :disabled="deleting"
        @click="emit('edit', gear)"
      >
        <Pencil class="size-4" aria-hidden="true" />
      </Button>
      <Button
        variant="ghostDestructive"
        size="icon-sm"
        :aria-label="t('gears.actions.delete')"
        :disabled="deleting"
        @click="emit('delete', gear)"
      >
        <Trash2 class="size-4" aria-hidden="true" />
      </Button>
    </div>
  </div>
</template>
