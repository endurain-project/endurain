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
          <label :for="`${modalId}Email`" class="form-label">{{ emailFieldLabel }}</label>
          <input
            :id="`${modalId}Email`"
            v-model="emailToEmit"
            type="email"
            class="form-control"
            :class="{ 'is-invalid': !isEmailValid }"
            :name="`${modalId}Email`"
            :placeholder="emailFieldLabel"
            :aria-label="emailFieldLabel"
            aria-describedby="validationEmailFeedback"
            required
          />
          <div id="validationEmailFeedback" class="invalid-feedback" v-if="!isEmailValid">
            {{ $t('usersAddEditUserModalComponent.addEditUserModalErrorEmailInvalid') }}
          </div>
          <div class="form-text" v-if="emailHelpText">{{ emailHelpText }}</div>
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
            :disabled="isLoading"
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
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
/**
 * ModalComponentEmailInput
 *
 * Reusable modal component for email input with RFC 5322 compliant validation.
 * Follows the same structure and patterns as ModalComponent.vue.
 *
 * Features:
 * - Real-time email validation feedback
 * - Loading state support
 * - Input sanitization
 * - Customizable button types (success, danger, warning, primary)
 *
 * @component
 */

// ============================================================================
// Section 1: Imports
// ============================================================================

// Vue composition API
import { ref, computed, onMounted, onUnmounted, type PropType } from 'vue'
// Composables
import { useBootstrapModal } from '@/composables/useBootstrapModal'
// Types
import type { ActionButtonType } from '@/types'
// Utils
import { isValidEmail, sanitizeInput } from '@/utils/validationUtils'

// ============================================================================
// Section 2: Props & Emits
// ============================================================================

const props = withDefaults(
  defineProps<{
    /** Unique identifier for the modal element */
    modalId: string
    /** Modal header title */
    title: string
    /** Label for the email input field */
    emailFieldLabel: string
    /** Optional help text displayed below input */
    emailHelpText?: string
    /** Default value for email input */
    emailDefaultValue?: string
    /** Button style type */
    actionButtonType: ActionButtonType
    /** Text displayed on action button */
    actionButtonText: string
    /** Loading state indicator */
    isLoading?: boolean
  }>(),
  {
    emailHelpText: '',
    emailDefaultValue: '',
    isLoading: false
  }
)

const emit = defineEmits<{
  emailToEmitAction: [email: string]
}>()

// ============================================================================
// Section 3: Composables & Stores
// ============================================================================

const { initializeModal, disposeModal } = useBootstrapModal()

// ============================================================================
// Section 4: Reactive State
// ============================================================================

const modalRef = ref<HTMLDivElement | null>(null)
const emailToEmit = ref(props.emailDefaultValue)

// ============================================================================
// Section 5: Computed Properties
// ============================================================================

/**
 * Validate email format using RFC 5322 compliant validation
 * Returns true if email is valid or empty (to avoid showing error on load)
 */
const isEmailValid = computed(() => {
  // Don't show validation error for empty input
  if (!emailToEmit.value) return true

  return isValidEmail(emailToEmit.value)
})

// ============================================================================
// Section 8: Main Logic
// ============================================================================

/**
 * Handle form submission
 * Validates and sanitizes email before emitting to parent
 * Only emits if email is non-empty and valid
 */
const submitAction = (): void => {
  if (!emailToEmit.value) return

  // Sanitize input before validation
  const sanitizedEmail = sanitizeInput(emailToEmit.value)

  // Only emit if email is valid
  if (isValidEmail(sanitizedEmail)) {
    emit('emailToEmitAction', sanitizedEmail)
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
