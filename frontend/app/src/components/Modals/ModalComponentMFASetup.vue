<template>
  <div
    ref="modalRef"
    class="modal fade"
    :id="modalId"
    tabindex="-1"
    :aria-labelledby="`${modalId}Title`"
    aria-hidden="true"
  >
    <div class="modal-dialog modal-dialog-centered">
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
          <div v-if="qrCodeData">
            <p>{{ instructions }}</p>
            <div class="text-center mb-3">
              <img :src="qrCodeData" alt="QR Code" class="img-fluid" style="max-width: 200px" />
            </div>
            <p>
              <strong>{{ secretLabel }}:</strong>
              <code class="ms-1">{{ mfaSecret }}</code>
            </p>
            <form @submit.prevent="handleSubmit">
              <label :for="`${modalId}VerificationCode`" class="form-label">
                <b>* {{ verificationCodeLabel }}</b>
              </label>
              <input
                :id="`${modalId}VerificationCode`"
                v-model="verificationCode"
                type="text"
                class="form-control"
                :name="`${modalId}VerificationCode`"
                :placeholder="verificationCodePlaceholder"
                :aria-label="verificationCodeLabel"
                required
              />
              <p class="mt-2">* {{ requiredFieldText }}</p>
              <div class="d-flex justify-content-end">
                <button
                  type="button"
                  class="btn btn-secondary me-2"
                  data-bs-dismiss="modal"
                  aria-label="Close modal"
                >
                  {{ cancelButtonText }}
                </button>
                <button
                  type="submit"
                  class="btn"
                  :class="{
                    'btn-success': actionButtonType === 'success',
                    'btn-danger': actionButtonType === 'danger',
                    'btn-warning': actionButtonType === 'warning',
                    'btn-primary': actionButtonType === 'primary'
                  }"
                  :disabled="!verificationCode || isLoading"
                  :aria-label="actionButtonText"
                >
                  <span
                    v-if="isLoading"
                    class="spinner-border spinner-border-sm me-2"
                    role="status"
                    aria-hidden="true"
                  ></span>
                  {{ actionButtonText }}
                </button>
              </div>
            </form>
          </div>
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

const props = defineProps({
  modalId: {
    type: String,
    required: true
  },
  title: {
    type: String,
    required: true
  },
  instructions: {
    type: String,
    required: true
  },
  qrCodeData: {
    type: String,
    required: true
  },
  mfaSecret: {
    type: String,
    required: true
  },
  secretLabel: {
    type: String,
    required: true
  },
  verificationCodeLabel: {
    type: String,
    required: true
  },
  verificationCodePlaceholder: {
    type: String,
    required: true
  },
  requiredFieldText: {
    type: String,
    required: true
  },
  cancelButtonText: {
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
  },
  isLoading: {
    type: Boolean,
    default: false
  }
})

const emit = defineEmits<{
  submitAction: [verificationCode: string]
}>()

const { modalInstance, initializeModal, showModal, hideModal, disposeModal } = useBootstrapModal()

const modalRef = ref<HTMLDivElement | null>(null)
const verificationCode = ref('')

const handleModalHidden = (): void => {
  verificationCode.value = ''
}

const handleSubmit = (): void => {
  if (verificationCode.value) {
    emit('submitAction', verificationCode.value)
  }
}

const show = (): void => {
  showModal()
}

const hide = (): void => {
  hideModal()
  verificationCode.value = ''
}

onMounted(async () => {
  await initializeModal(modalRef)

  // Listen for modal hidden event to reset form
  if (modalRef.value) {
    modalRef.value.addEventListener('hidden.bs.modal', handleModalHidden)
  }
})

onUnmounted(() => {
  if (modalRef.value) {
    modalRef.value.removeEventListener('hidden.bs.modal', handleModalHidden)
  }
  disposeModal()
})

defineExpose({
  show,
  hide
})
</script>
