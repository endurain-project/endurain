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
// Vue composition API
import { ref, onMounted, onUnmounted, type PropType } from 'vue'
// Composables
import { useBootstrapModal } from '@/composables/useBootstrapModal'
// Types
import type { ActionButtonType } from '@/types'

interface DateRange {
  startDate: string
  endDate: string
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

const { initializeModal, disposeModal } = useBootstrapModal()

const modalRef = ref<HTMLDivElement | null>(null)
const startDate = ref('')
const endDate = ref('')

const setDefaultDates = (): void => {
  const today = new Date()
  const sevenDaysAgo = new Date(today)
  sevenDaysAgo.setDate(today.getDate() - 7)

  // Format to YYYY-MM-DD
  startDate.value = sevenDaysAgo.toISOString().split('T')[0] || ''
  endDate.value = today.toISOString().split('T')[0] || ''
}

const emitDates = (): void => {
  emit('datesToEmitAction', {
    startDate: startDate.value,
    endDate: endDate.value
  })
}

onMounted(async () => {
  await initializeModal(modalRef)
  setDefaultDates()
})

onUnmounted(() => {
  disposeModal()
})
</script>
