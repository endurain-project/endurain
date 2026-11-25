<script setup lang="ts">
import type { HTMLAttributes } from 'vue'
import { computed } from 'vue'
import { TabsTrigger, type TabsTriggerProps, useForwardProps } from 'reka-ui'

import { cn } from '@/lib/utils'
import { tabsTriggerClass } from '.'

const props = defineProps<TabsTriggerProps & { class?: HTMLAttributes['class'] }>()

const delegatedProps = computed(() => {
  const { class: _class, ...delegated } = props
  return delegated
})

const forwarded = useForwardProps(delegatedProps)
</script>

<template>
  <TabsTrigger
    data-slot="tabs-trigger"
    v-bind="forwarded"
    :class="
      cn(
        tabsTriggerClass,
        'data-[state=active]:bg-card data-[state=active]:text-foreground data-[state=active]:shadow-sm',
        props.class,
      )
    "
  >
    <slot />
  </TabsTrigger>
</template>
