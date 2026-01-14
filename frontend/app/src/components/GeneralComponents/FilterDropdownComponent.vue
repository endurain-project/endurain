<template>
  <div class="dropdown">
    <button
      class="btn btn-sm btn-link link-body-emphasis dropdown-toggle"
      type="button"
      data-bs-toggle="dropdown"
      :aria-expanded="false"
      :aria-label="ariaLabel"
    >
      <font-awesome-icon :icon="['fas', 'filter']" />
    </button>
    <ul class="dropdown-menu ps-3">
      <li v-for="option in options" :key="option.id">
        <div class="form-check">
          <input
            class="form-check-input"
            type="checkbox"
            :id="option.id"
            :checked="modelValue[option.id]"
            @change="handleChange(option.id, ($event.target as HTMLInputElement).checked)"
          />
          <label class="form-check-label" :for="option.id">
            {{ option.label }}
          </label>
        </div>
      </li>
    </ul>
  </div>
</template>

<script setup lang="ts">
import { useI18n } from 'vue-i18n'

/**
 * Represents a single filter option.
 *
 * @property id - Unique identifier for the filter option.
 * @property label - Display label for the filter option.
 */
interface FilterOption {
  id: string
  label: string
}

/**
 * Props for the FilterDropdownComponent.
 *
 * @property options - Array of filter options to display.
 * @property modelValue - Object containing the current state of each filter option.
 * @property ariaLabel - Accessible label for the filter button.
 */
interface Props {
  options: FilterOption[]
  modelValue: Record<string, boolean>
  ariaLabel?: string
}

const { t } = useI18n()

const props = withDefaults(defineProps<Props>(), {
  ariaLabel: 'Filter options'
})

const emit = defineEmits<{
  'update:modelValue': [value: Record<string, boolean>]
}>()

/**
 * Handles checkbox state changes and emits updated filter values.
 *
 * @param optionId - The id of the filter option that changed.
 * @param checked - The new checked state.
 */
function handleChange(optionId: string, checked: boolean): void {
  emit('update:modelValue', {
    ...props.modelValue,
    [optionId]: checked
  })
}
</script>
