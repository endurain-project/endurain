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
          <!-- First string field -->
          <div class="mb-3">
            <label :for="`${modalId}FirstInput`" class="form-label">
              <b>* {{ firstFieldLabel }}</b>
            </label>
            <input
              :id="`${modalId}FirstInput`"
              v-model="firstToEmit"
              class="form-control"
              :type="firstFieldType"
              :name="`${modalId}FirstInput`"
              :placeholder="firstFieldLabel"
              :aria-label="firstFieldLabel"
              required
            />
          </div>
          <!-- Second string field -->
          <div>
            <label :for="`${modalId}SecondInput`" class="form-label">
              <b>* {{ secondFieldLabel }}</b>
            </label>
            <input
              :id="`${modalId}SecondInput`"
              v-model="secondToEmit"
              class="form-control"
              :type="secondFieldType"
              :name="`${modalId}SecondInput`"
              :placeholder="secondFieldLabel"
              :aria-label="secondFieldLabel"
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
  firstToEmit: string
  secondToEmit: string
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
  firstFieldLabel: {
    type: String,
    required: true
  },
  firstFieldType: {
    type: String,
    default: 'text'
  },
  firstDefaultValue: {
    type: String,
    default: ''
  },
  secondFieldLabel: {
    type: String,
    required: true
  },
  secondFieldType: {
    type: String,
    default: 'text'
  },
  secondDefaultValue: {
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
const firstToEmit = ref(props.firstDefaultValue)
const secondToEmit = ref(props.secondDefaultValue)

const submitAction = (): void => {
  emit('fieldsToEmitAction', {
    firstToEmit: firstToEmit.value,
    secondToEmit: secondToEmit.value
  })
}

onMounted(async () => {
  await initializeModal(modalRef)
})

onUnmounted(() => {
  disposeModal()
})
</script>
