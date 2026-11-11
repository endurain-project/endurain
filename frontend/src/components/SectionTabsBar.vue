<script setup lang="ts">
import { computed } from 'vue'
import { Check, ChevronDown } from '@lucide/vue'

import { Button } from '@/components/ui/button'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { TabsList, TabsTrigger } from '@/components/ui/tabs'

/** One entry of the bar. */
export interface SectionTab {
  value: string
  label: string
  /** Shows a marker for unsaved edits. */
  dirty?: boolean
}

const props = defineProps<{
  tabs: SectionTab[]
  /** Accessible name of the tab row. */
  label: string
  /** Accessible name of the unsaved-edits marker; needed only when a tab can be dirty. */
  unsavedLabel?: string
}>()

const active = defineModel<string>({ required: true })
const activeEntry = computed(() => props.tabs.find((tab) => tab.value === active.value))
</script>

<template>
  <!-- Below lg: a menu button, like the settings zone menu above, instead of a tab row. -->
  <DropdownMenu>
    <DropdownMenuTrigger as-child>
      <Button variant="outline" class="w-full justify-between lg:hidden">
        <span class="flex min-w-0 items-center gap-2">
          <span class="truncate">{{ activeEntry?.label }}</span>
          <span
            v-if="activeEntry?.dirty"
            role="img"
            class="size-2 shrink-0 rounded-full bg-brand"
            :aria-label="unsavedLabel"
          />
        </span>
        <ChevronDown class="size-4 shrink-0 opacity-60" aria-hidden="true" />
      </Button>
    </DropdownMenuTrigger>
    <DropdownMenuContent align="start" class="w-56">
      <DropdownMenuItem v-for="tab in tabs" :key="tab.value" @select="active = tab.value">
        <span class="truncate">{{ tab.label }}</span>
        <span
          v-if="tab.dirty"
          role="img"
          class="size-2 shrink-0 rounded-full bg-brand"
          :aria-label="unsavedLabel"
        />
        <Check v-if="tab.value === active" class="ml-auto size-4 shrink-0" aria-hidden="true" />
      </DropdownMenuItem>
    </DropdownMenuContent>
  </DropdownMenu>

  <TabsList class="hidden lg:inline-flex" :aria-label="label">
    <TabsTrigger v-for="tab in tabs" :key="tab.value" :value="tab.value">
      {{ tab.label }}
      <span
        v-if="tab.dirty"
        role="img"
        class="ml-2 size-2 rounded-full bg-brand"
        :aria-label="unsavedLabel"
      />
    </TabsTrigger>
  </TabsList>
</template>
