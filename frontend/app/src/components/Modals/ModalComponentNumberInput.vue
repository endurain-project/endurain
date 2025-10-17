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
          <label :for="`${modalId}NumberInput`" class="form-label">
            <b>* {{ numberFieldLabel }}</b>
          </label>
          <input
            :id="`${modalId}NumberInput`"
            v-model="numberToEmit"
            class="form-control"
            type="number"
            :name="`${modalId}NumberInput`"
            :placeholder="numberFieldLabel"
            :aria-label="numberFieldLabel"
            required
          />
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
            :disabled="!isValid"
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
 * ModalComponentNumberInput
 *
 * Reusable modal component for numeric input with configurable action button types.
 * Follows the same structure and patterns as ModalComponent.vue.
 *
 * @component
 */

// ============================================================================
// Section 1: Imports
// ============================================================================

// Vue composition API
import { ref, onMounted, onUnmounted, computed, type PropType } from 'vue'
// Composables
import { useBootstrapModal } from '@/composables/useBootstrapModal'
// Types
import type { ActionButtonType } from '@/types'

// ============================================================================
// Section 2: Props & Emits
// ============================================================================

const props = defineProps({
  modalId: {
    type: String,
    required: true
  },
  title: {
    type: String,
    required: true
  },
  numberFieldLabel: {
    type: String,
    required: true
  },
  numberDefaultValue: {
    type: [Number, null] as PropType<number | null>,
    default: null
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
  numberToEmitAction: [value: number]
}>()

// ============================================================================
// Section 3: Composables & Stores
// ============================================================================

const { initializeModal, disposeModal } = useBootstrapModal()

// ============================================================================
// Section 4: Reactive State
// ============================================================================

const modalRef = ref<HTMLDivElement | null>(null)
const numberToEmit = ref<number | null>(props.numberDefaultValue)

// ============================================================================
// Section 7: Validation Logic
// ============================================================================

/**
 * Check if the input has a valid numeric value
 */
const isValid = computed(() => numberToEmit.value !== null && numberToEmit.value !== undefined)

// ============================================================================
// Section 8: Main Logic
// ============================================================================

/**
 * Handle submit action and emit the numeric value
 */
const submitAction = (): void => {
  if (isValid.value && numberToEmit.value !== null && numberToEmit.value !== undefined) {
    emit('numberToEmitAction', numberToEmit.value)
  }
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
