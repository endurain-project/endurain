<script setup lang="ts">
import { computed, type HTMLAttributes } from 'vue'

import type { GearType } from '@/features/gears/types'
import { presentGearType } from '@/features/gears/utils/gearType'

const props = defineProps<{
  /** The gear type. */
  type: GearType
  class?: HTMLAttributes['class']
}>()

const icon = computed(() => presentGearType(props.type).icon)
</script>

<template>
  <component :is="icon" :class="props.class" aria-hidden="true" />
</template>
