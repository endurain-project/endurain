<template>
  <div
    class="modal fade"
    :id="`${modalId}`"
    tabindex="-1"
    :aria-labelledby="`${modalId}`"
    aria-hidden="true"
  >
    <div class="modal-dialog">
      <div class="modal-content">
        <div class="modal-header">
          <h1 class="modal-title fs-5" :id="`${modalId}`">{{ title }}</h1>
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
            type="email"
            class="form-control"
            :class="{ 'is-invalid': !isEmailValid }"
            :name="`${modalId}Email`"
            :id="`${modalId}Email`"
            v-model="emailToEmit"
            :placeholder="emailFieldLabel"
            required
          />
          <div id="validationEmailFeedback" class="invalid-feedback" v-if="!isEmailValid">
            {{ $t('usersAddEditUserModalComponent.addEditUserModalErrorEmailInvalid') }}
          </div>
          <div class="form-text" v-if="emailHelpText">{{ emailHelpText }}</div>
        </div>
        <div class="modal-footer">
          <button type="button" class="btn btn-secondary" data-bs-dismiss="modal">
            {{ $t('generalItems.buttonClose') }}
          </button>
          <button
            type="button"
            @click="submitAction()"
            class="btn"
            :class="{
              'btn-success': actionButtonType === 'success',
              'btn-danger': actionButtonType === 'danger',
              'btn-warning': actionButtonType === 'warning',
              'btn-primary': actionButtonType === 'primary'
            }"
            :disabled="isLoading"
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
 * ModalComponentEmailInput Component
 *
 * A reusable Bootstrap modal component for email input operations.
 * Features:
 * - RFC 5322 compliant email validation
 * - Real-time validation feedback
 * - Loading state support
 * - Customizable button types (success, danger, warning, primary)
 * - Input sanitization
 *
 * @component
 */

// Vue composition API
import { ref, computed, type Ref, type ComputedRef } from 'vue'
// Types
import type { ActionButtonType } from '@/types'
// Utils
import { isValidEmail, sanitizeInput } from '@/utils/validationUtils'

// ============================================================================
// Types
// ============================================================================

/**
 * Component props interface
 */
interface Props {
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
}

/**
 * Component emits interface
 */
interface Emits {
  (e: 'emailToEmitAction', email: string): void
}

// ============================================================================
// Props & Emits
// ============================================================================

const props = withDefaults(defineProps<Props>(), {
  emailHelpText: '',
  emailDefaultValue: '',
  isLoading: false
})

const emit = defineEmits<Emits>()

// ============================================================================
// State
// ============================================================================

/**
 * Email input value
 * Initialized with default value from props
 */
const emailToEmit: Ref<string> = ref(props.emailDefaultValue)

// ============================================================================
// Computed Properties
// ============================================================================

/**
 * Validate email format using RFC 5322 compliant validation
 * Returns true if email is valid or empty (to avoid showing error on load)
 *
 * @returns {boolean} Email validation state
 */
const isEmailValid: ComputedRef<boolean> = computed(() => {
  // Don't show validation error for empty input
  if (!emailToEmit.value) return true

  return isValidEmail(emailToEmit.value)
})

// ============================================================================
// Actions
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
</script>
