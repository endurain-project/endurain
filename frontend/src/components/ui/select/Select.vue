<script setup lang="ts" generic="T extends string | number | null = string">
import type { HTMLAttributes } from 'vue'
import { ChevronDown } from '@lucide/vue'

import { cn } from '@/lib/utils'
import { inputFieldClass } from '@/components/ui/input/fieldClasses'

// Attributes (id, disabled, aria-*) belong on the native select, not the wrapper.
defineOptions({ inheritAttrs: false })

/**
 * `class` styles the wrapper, which owns the control's size: `h-9` matches the
 * default button height, and callers override it (e.g. `h-8`, `w-full`).
 */
const props = defineProps<{ class?: HTMLAttributes['class'] }>()

/**
 * Two-way bound value for the select. Generic over the option value type so
 * callers binding a narrow string union (e.g. a gender or currency code), or a
 * nullable id with a `null` "none" option, keep full type-safety on both the
 * model and the rendered `<option>` values.
 */
const model = defineModel<T>({ required: true })
</script>

<template>
  <div :class="cn('relative inline-flex h-9', props.class)">
    <!-- appearance-none drops the native control, which ignores padding and height in WebKit. -->
    <select
      v-model="model"
      v-bind="$attrs"
      data-slot="select"
      :class="cn(inputFieldClass, 'peer h-full w-full appearance-none py-0 pe-9')"
    >
      <slot />
    </select>
    <ChevronDown
      class="pointer-events-none absolute end-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground peer-disabled:opacity-50"
      aria-hidden="true"
    />
  </div>
</template>
