<script setup lang="ts">
import type { HTMLAttributes } from 'vue'
import { computed } from 'vue'
import { TabsList, type TabsListProps, useForwardProps } from 'reka-ui'

import { cn } from '@/lib/utils'
import { tabsListClass } from '.'

const props = defineProps<TabsListProps & { class?: HTMLAttributes['class'] }>()

const delegatedProps = computed(() => {
  const { class: _class, ...delegated } = props
  return delegated
})

const forwarded = useForwardProps(delegatedProps)
</script>

<template>
  <TabsList data-slot="tabs-list" v-bind="forwarded" :class="cn(tabsListClass, props.class)">
    <slot />
  </TabsList>
</template>
