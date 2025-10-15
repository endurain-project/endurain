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
          <h5 class="modal-title" :id="`${modalId}Title`">{{ title }}</h5>
          <button
            type="button"
            class="btn-close"
            data-bs-dismiss="modal"
            aria-label="Close"
          ></button>
        </div>
        <div class="modal-body">
          <div class="mb-3">
            <label :for="`${modalId}StartDate`" class="form-label">{{
              $t('generalItems.startDateLabel')
            }}</label>
            <input
              type="date"
              class="form-control"
              :id="`${modalId}StartDate`"
              v-model="startDate"
              aria-label="Start date input"
            />
          </div>
          <div class="mb-3">
            <label :for="`${modalId}EndDate`" class="form-label">{{
              $t('generalItems.endDateLabel')
            }}</label>
            <input
              type="date"
              class="form-control"
              :id="`${modalId}EndDate`"
              v-model="endDate"
              aria-label="End date input"
            />
          </div>
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
            class="btn"
            :class="{
              'btn-success': actionButtonType === 'success',
              'btn-danger': actionButtonType === 'danger',
              'btn-warning': actionButtonType === 'warning',
              'btn-primary': actionButtonType === 'primary'
            }"
            @click="emitDates"
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
 * ModalComponentDateRangeInput
 *
 * Modal component for selecting a date range with start and end dates.
 * Defaults to last 7 days when mounted.
 *
 * @component
 */

// Vue composition API
import { ref, onMounted, onUnmounted, type PropType } from 'vue'
// Internationalization
import { useI18n } from 'vue-i18n'
// Composables
import { useBootstrapModal } from '@/composables/useBootstrapModal'
// Types
import type { ActionButtonType } from '@/types'

// ============================================================================
// Types
// ============================================================================

interface DateRange {
  startDate: string
  endDate: string
}

// ============================================================================
// Props & Emits
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
  actionButtonType: {
    type: String as PropType<ActionButtonType>,
    default: 'primary',
    validator: (value: string) => ['success', 'danger', 'warning', 'primary'].includes(value)
  },
  actionButtonText: {
    type: String,
    required: true
  }
})

const emit = defineEmits<{
  datesToEmitAction: [dateRange: DateRange]
}>()

// ============================================================================
// Composables & State
// ============================================================================

const { t } = useI18n()
const { initializeModal, disposeModal } = useBootstrapModal()

// ============================================================================
// Reactive State
// ============================================================================

const modalRef = ref<HTMLDivElement | null>(null)
const startDate = ref('')
const endDate = ref('')

// ============================================================================
// Main Logic
// ============================================================================

/**
 * Set default date range to last 7 days
 */
const setDefaultDates = (): void => {
  const today = new Date()
  const sevenDaysAgo = new Date(today)
  sevenDaysAgo.setDate(today.getDate() - 7)

  // Format to YYYY-MM-DD
  startDate.value = sevenDaysAgo.toISOString().split('T')[0] || ''
  endDate.value = today.toISOString().split('T')[0] || ''
}

/**
 * Emit selected date range to parent component
 */
const emitDates = (): void => {
  emit('datesToEmitAction', {
    startDate: startDate.value,
    endDate: endDate.value
  })
}

// ============================================================================
// Lifecycle Hooks
// ============================================================================

/**
 * Initialize modal and set default dates on mount
 */
onMounted(async () => {
  await initializeModal(modalRef)
  setDefaultDates()
})

/**
 * Clean up modal on unmount
 */
onUnmounted(() => {
  disposeModal()
})
</script>
