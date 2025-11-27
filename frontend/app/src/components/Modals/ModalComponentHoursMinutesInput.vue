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
          <div class="input-group mb-3">
            <!-- Hours field -->
            <input
              :id="`${modalId}HoursInput`"
              v-model="hoursToEmit"
              class="form-control"
              type="number"
              :name="`${modalId}HoursInput`"
              :placeholder="hoursFieldLabel"
              :aria-label="hoursFieldLabel"
              required
            />
            <span class="input-group-text" id="basic-addon2">{{ hoursFieldLabel }}</span>
            <!-- Minutes field -->
            <input
              :id="`${modalId}MinutesInput`"
              v-model="minutesToEmit"
              class="form-control"
              type="number"
              :name="`${modalId}MinutesInput`"
              :placeholder="minutesFieldLabel"
              :aria-label="minutesFieldLabel"
              required
            />
            <span class="input-group-text" id="basic-addon2">{{ minutesFieldLabel }}</span>
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
// Vue composition API
import { ref, onMounted, onUnmounted, type PropType } from 'vue'
// Composables
import { useBootstrapModal } from '@/composables/useBootstrapModal'

import { returnHoursMinutesFromSeconds, returnSecondsFromHoursMinutes } from '@/utils/dateTimeUtils'
// Types
import type { ActionButtonType } from '@/types'

const props = defineProps({
  modalId: {
    type: String,
    required: true
  },
  title: {
    type: String,
    required: true
  },
  hoursFieldLabel: {
    type: String,
    required: true
  },
  secondsDefaultValue: {
    type: Number,
    default: 28800
  },
  minutesFieldLabel: {
    type: String,
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
  fieldsToEmitAction: [value: number]
}>()

const { initializeModal, disposeModal } = useBootstrapModal()

const modalRef = ref<HTMLDivElement | null>(null)
const { hours, minutes } = returnHoursMinutesFromSeconds(props.secondsDefaultValue)
const hoursToEmit = ref(hours)
const minutesToEmit = ref(minutes)

const submitAction = (): void => {
  const secondsToEmit = returnSecondsFromHoursMinutes(hoursToEmit.value, minutesToEmit.value)
  emit('fieldsToEmitAction', secondsToEmit)
}

onMounted(async () => {
  await initializeModal(modalRef)
})

onUnmounted(() => {
  disposeModal()
})
</script>
