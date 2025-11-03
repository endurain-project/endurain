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
          <!-- Number field -->
          <div class="mb-3">
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
          <!-- String field -->
          <div>
            <label :for="`${modalId}StringInput`" class="form-label">
              <b>* {{ stringFieldLabel }}</b>
            </label>
            <input
              :id="`${modalId}StringInput`"
              v-model="stringToEmit"
              class="form-control"
              type="text"
              :name="`${modalId}StringInput`"
              :placeholder="stringFieldLabel"
              :aria-label="stringFieldLabel"
              required
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
// Types
import type { ActionButtonType } from '@/types'

interface FieldsEmitPayload {
  numberToEmit: number
  stringToEmit: string
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
  numberFieldLabel: {
    type: String,
    required: true
  },
  numberDefaultValue: {
    type: Number,
    default: 7
  },
  stringFieldLabel: {
    type: String,
    required: true
  },
  stringDefaultValue: {
    type: String,
    default: ''
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
  fieldsToEmitAction: [payload: FieldsEmitPayload]
}>()

const { initializeModal, disposeModal } = useBootstrapModal()

const modalRef = ref<HTMLDivElement | null>(null)
const numberToEmit = ref(props.numberDefaultValue)
const stringToEmit = ref(props.stringDefaultValue)

const submitAction = (): void => {
  emit('fieldsToEmitAction', {
    numberToEmit: numberToEmit.value,
    stringToEmit: stringToEmit.value
  })
}

onMounted(async () => {
  await initializeModal(modalRef)
})

onUnmounted(() => {
  disposeModal()
})
</script>
