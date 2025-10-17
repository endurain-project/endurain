<template>
  <div
    ref="modalRef"
    class="modal fade"
    :id="modalId"
    tabindex="-1"
    :aria-labelledby="`${modalId}Title`"
    aria-hidden="true"
  >
    <div class="modal-dialog">
      <div class="modal-content">
        <div class="modal-header">
          <h1 class="modal-title fs-5" :id="`${modalId}Title`">{{ title }}</h1>
          <button
            type="button"
            class="btn-close"
            data-bs-dismiss="modal"
            aria-label="Close"
          ></button>
        </div>
        <div class="modal-body">
          <label :for="`${modalId}Select`" class="form-label">
            <b>* {{ selectFieldLabel }}</b>
          </label>
          <select
            :id="`${modalId}Select`"
            v-model="optionToEmit"
            class="form-select"
            :name="`${modalId}Select`"
            :aria-label="selectFieldLabel"
            required
          >
            <option v-for="select in selectOptions" :key="select.id" :value="select.id">
              {{ select.name }}
            </option>
          </select>
        </div>
        <div class="modal-footer">
          <button
            type="button"
            class="btn btn-secondary"
            data-bs-dismiss="modal"
            aria-label="Close modal"
          >
            {{ $t('generalItems.buttonClose') }}
          </button>
          <button
            type="button"
            @click="submitAction"
            class="btn"
            :class="{
              'btn-success': actionButtonType === 'success',
              'btn-danger': actionButtonType === 'danger',
              'btn-warning': actionButtonType === 'warning',
              'btn-primary': actionButtonType === 'primary'
            }"
            data-bs-dismiss="modal"
            :aria-label="actionButtonText"
          >
            {{ actionButtonText }}
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
/**
 * ModalComponentSelectInput
 *
 * Reusable modal component for dropdown/select input with configurable action button types.
 * Follows the same structure and patterns as ModalComponent.vue.
 *
 * @component
 */

// ============================================================================
// Section 1: Imports
// ============================================================================

// Vue composition API
import { ref, onMounted, onUnmounted, type PropType } from 'vue'
// Composables
import { useBootstrapModal } from '@/composables/useBootstrapModal'
// Types
import type { ActionButtonType } from '@/types'

// ============================================================================
// Section 2: Props & Emits
// ============================================================================

interface SelectOption {
  id: number
  name: string
}

const props = defineProps({
  modalId: {
    type: String,
    required: true
  },
  title: {
    type: String,
    required: true
  },
  selectFieldLabel: {
    type: String,
    required: true
  },
  selectOptions: {
    type: Array as PropType<SelectOption[]>,
    required: true
  },
  selectCurrentOption: {
    type: Number,
    required: true
  },
  actionButtonType: {
    type: String as PropType<ActionButtonType>,
    required: true,
    validator: (value: string) => ['success', 'danger', 'warning', 'primary'].includes(value)
  },
  actionButtonText: {
    type: String,
    required: true
  }
})

const emit = defineEmits<{
  optionToEmitAction: [value: number]
}>()

// ============================================================================
// Section 3: Composables & Stores
// ============================================================================

const { initializeModal, disposeModal } = useBootstrapModal()

// ============================================================================
// Section 4: Reactive State
// ============================================================================

const modalRef = ref<HTMLDivElement | null>(null)
const optionToEmit = ref(props.selectCurrentOption)

// ============================================================================
// Section 8: Main Logic
// ============================================================================

/**
 * Handle submit action and emit the selected option value
 */
const submitAction = (): void => {
  emit('optionToEmitAction', optionToEmit.value)
}

// ============================================================================
// Section 9: Lifecycle Hooks
// ============================================================================

/**
 * Initialize modal on mount
 */
onMounted(async () => {
  await initializeModal(modalRef)
})

/**
 * Clean up modal on unmount
 */
onUnmounted(() => {
  disposeModal()
})
</script>
