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
          <a
            type="button"
            @click="submitAction()"
            class="btn"
            :class="{
              'btn-success': actionButtonType === 'success',
              'btn-danger': actionButtonType === 'danger',
              'btn-warning': actionButtonType === 'warning',
              'btn-primary': actionButtonType === 'loading'
            }"
            :disabled="isLoading"
            ><span
              v-if="isLoading"
              class="spinner-border spinner-border-sm me-2"
              role="status"
              aria-hidden="true"
            ></span
            >{{ actionButtonText }}</a
          >
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed } from 'vue'

const props = defineProps({
  modalId: {
    type: String,
    required: true
  },
  title: {
    type: String,
    required: true
  },
  emailFieldLabel: {
    type: String,
    required: true
  },
  emailHelpText: {
    type: String,
    default: ''
  },
  emailDefaultValue: {
    type: String,
    default: ''
  },
  actionButtonType: {
    type: String,
    required: true
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

const emit = defineEmits(['emailToEmitAction'])
const isEmailValid = computed(() => {
  const emailRegex = /^[^\s@]{1,}@[^\s@]{2,}\.[^\s@]{2,}$/
  return emailRegex.test(emailToEmit.value)
})

const emailToEmit = ref(props.emailDefaultValue)

function submitAction() {
  if (emailToEmit.value) {
    emit('emailToEmitAction', emailToEmit.value)
  }
}
</script>
