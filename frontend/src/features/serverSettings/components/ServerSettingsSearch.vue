<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, useId } from 'vue'
import { useI18n } from 'vue-i18n'
import { Search } from '@lucide/vue'

import type { SettingsSearchResult } from '@/features/serverSettings/searchIndex'

import { Input } from '@/components/ui/input'
import { searchSettings } from '@/features/serverSettings/searchIndex'

const emit = defineEmits<{
  /** The user picked a setting to jump to. */
  select: [result: SettingsSearchResult]
}>()

const { t } = useI18n()

const inputId = useId()
const listId = `${inputId}-list`
const query = ref('')
const isOpen = ref(false)
const activeIndex = ref(0)

const results = computed(() =>
  searchSettings(
    query.value,
    (key) => t(key),
    (tab) => t(`settings.server.tabs.${tab}`),
  ),
)
const showList = computed(() => isOpen.value && query.value.trim() !== '')

/**
 * The DOM id of a result row, so the input can point at the active one.
 *
 * @param index - The row position.
 * @returns The element id.
 */
function optionId(index: number): string {
  return `${inputId}-option-${index}`
}

/**
 * Jumps to a result and clears the box.
 *
 * @param result - The chosen result.
 */
function choose(result: SettingsSearchResult): void {
  emit('select', result)
  query.value = ''
  isOpen.value = false
  document.getElementById(inputId)?.blur()
}

/**
 * Keyboard control of the list: arrows move, Enter picks, Escape closes.
 *
 * @param event - The keydown event from the input.
 */
function onKeydown(event: KeyboardEvent): void {
  if (event.key === 'Escape') {
    isOpen.value = false
    return
  }
  if (!showList.value || results.value.length === 0) {
    return
  }
  if (event.key === 'ArrowDown') {
    event.preventDefault()
    activeIndex.value = (activeIndex.value + 1) % results.value.length
  } else if (event.key === 'ArrowUp') {
    event.preventDefault()
    activeIndex.value = (activeIndex.value - 1 + results.value.length) % results.value.length
  } else if (event.key === 'Enter') {
    event.preventDefault()
    const result = results.value[activeIndex.value]
    if (result) {
      choose(result)
    }
  }
}

/** Opens the list and restarts from the first row whenever the query changes. */
function onInput(): void {
  isOpen.value = true
  activeIndex.value = 0
}

/**
 * Focuses the box on `/`, unless the user is already typing somewhere.
 *
 * @param event - The window keydown event.
 */
function onWindowKeydown(event: KeyboardEvent): void {
  if (event.key !== '/' || event.ctrlKey || event.metaKey || event.altKey) {
    return
  }
  const target = event.target
  if (
    target instanceof HTMLElement &&
    (target.isContentEditable || ['INPUT', 'SELECT', 'TEXTAREA'].includes(target.tagName))
  ) {
    return
  }
  event.preventDefault()
  document.getElementById(inputId)?.focus()
}

onMounted(() => window.addEventListener('keydown', onWindowKeydown))
onBeforeUnmount(() => window.removeEventListener('keydown', onWindowKeydown))
</script>

<template>
  <div class="relative w-full lg:w-72">
    <Search
      class="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground"
      aria-hidden="true"
    />
    <Input
      :id="inputId"
      v-model="query"
      type="search"
      class="w-full pl-9"
      role="combobox"
      autocomplete="off"
      aria-autocomplete="list"
      :aria-expanded="showList"
      :aria-controls="listId"
      :aria-activedescendant="showList && results.length > 0 ? optionId(activeIndex) : undefined"
      :aria-label="t('settings.server.search.placeholder')"
      :placeholder="t('settings.server.search.placeholder')"
      @input="onInput"
      @focus="isOpen = true"
      @blur="isOpen = false"
      @keydown="onKeydown"
    />

    <ul
      v-if="showList"
      :id="listId"
      role="listbox"
      class="absolute right-0 z-20 mt-1 flex max-h-80 w-full min-w-72 flex-col overflow-y-auto rounded-input border border-border bg-card p-1 shadow-md"
    >
      <li
        v-for="(result, index) in results"
        :id="optionId(index)"
        :key="result.entry.id"
        role="option"
        :aria-selected="index === activeIndex"
        class="flex cursor-pointer flex-col rounded-input px-3 py-2"
        :class="index === activeIndex ? 'bg-muted' : ''"
        @mousedown.prevent
        @mouseenter="activeIndex = index"
        @click="choose(result)"
      >
        <span class="text-body">{{ result.label }}</span>
        <span class="text-meta">
          {{ result.tabLabel }}<template v-if="result.section"> › {{ result.section }}</template>
        </span>
      </li>
      <li v-if="results.length === 0" role="presentation" class="px-3 py-2 text-meta">
        {{ t('settings.server.search.noResults') }}
      </li>
    </ul>
  </div>
</template>
