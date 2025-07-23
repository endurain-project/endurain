<!-- Example usage of ConfirmComponent -->
<template>
  <div class="container mt-4">
    <h2>ConfirmComponent Examples</h2>
    
    <!-- Basic Usage -->
    <div class="mb-3">
      <button class="btn btn-danger" @click="showBasicConfirm">
        Delete Item (Basic)
      </button>
    </div>
    
    <!-- Custom Buttons -->
    <div class="mb-3">
      <button class="btn btn-warning" @click="showCustomButtons">
        Custom Buttons
      </button>
    </div>
    
    <!-- Large Modal with HTML Content -->
    <div class="mb-3">
      <button class="btn btn-info" @click="showLargeModal">
        Large Modal with HTML
      </button>
    </div>
    
    <!-- Three Button Modal -->
    <div class="mb-3">
      <button class="btn btn-success" @click="showThreeButtonModal">
        Three Button Modal
      </button>
    </div>

    <!-- Basic Confirm Modal -->
    <ConfirmComponent
      ref="basicConfirmRef"
      title="Delete Confirmation"
      content="Are you sure you want to delete this item? This action cannot be undone."
      @confirm="handleBasicConfirm"
      @cancel="handleCancel"
    />

    <!-- Custom Buttons Modal -->
    <ConfirmComponent
      ref="customButtonsRef"
      title="Save Changes"
      content="Do you want to save your changes before leaving?"
      :buttons="customButtons"
      @button-click="handleCustomButtonClick"
    />

    <!-- Large Modal -->
    <ConfirmComponent
      ref="largeModalRef"
      title="Terms and Conditions"
      :content="htmlContent"
      size="lg"
      :buttons="termsButtons"
      @button-click="handleTermsClick"
    />

    <!-- Three Button Modal -->
    <ConfirmComponent
      ref="threeButtonRef"
      title="Unsaved Changes"
      content="You have unsaved changes. What would you like to do?"
      :buttons="threeButtons"
      @button-click="handleThreeButtonClick"
    />

    <!-- Result Display -->
    <div v-if="result" class="alert alert-info mt-3">
      <strong>Result:</strong> {{ result }}
    </div>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import ConfirmComponent from './ConfirmComponent.vue'

const basicConfirmRef = ref(null)
const customButtonsRef = ref(null)
const largeModalRef = ref(null)
const threeButtonRef = ref(null)
const result = ref('')

// Custom button configurations
const customButtons = [
  {
    label: 'Don\'t Save',
    class: 'btn btn-secondary',
    action: 'dont-save',
    dismiss: true
  },
  {
    label: 'Save',
    class: 'btn btn-success',
    action: 'save',
    dismiss: true
  }
]

const termsButtons = [
  {
    label: 'Decline',
    class: 'btn btn-outline-danger',
    action: 'decline',
    dismiss: true
  },
  {
    label: 'Accept',
    class: 'btn btn-primary',
    action: 'accept',
    dismiss: true
  }
]

const threeButtons = [
  {
    label: 'Cancel',
    class: 'btn btn-secondary',
    action: 'cancel',
    dismiss: true
  },
  {
    label: 'Don\'t Save',
    class: 'btn btn-outline-danger',
    action: 'dont-save',
    dismiss: true
  },
  {
    label: 'Save',
    class: 'btn btn-success',
    action: 'save',
    dismiss: true
  }
]

const htmlContent = `
  <h6>Terms and Conditions</h6>
  <p>By using this application, you agree to:</p>
  <ul>
    <li>Follow all <strong>community guidelines</strong></li>
    <li>Respect other users' privacy</li>
    <li>Not share sensitive information</li>
    <li>Report any bugs or issues</li>
  </ul>
  <p><small class="text-muted">Last updated: July 2025</small></p>
`

// Event handlers
const showBasicConfirm = () => {
  basicConfirmRef.value.show()
}

const showCustomButtons = () => {
  customButtonsRef.value.show()
}

const showLargeModal = () => {
  largeModalRef.value.show()
}

const showThreeButtonModal = () => {
  threeButtonRef.value.show()
}

const handleBasicConfirm = () => {
  result.value = 'Item deleted successfully!'
}

const handleCancel = () => {
  result.value = 'Action cancelled'
}

const handleCustomButtonClick = (button) => {
  if (button.action === 'save') {
    result.value = 'Changes saved!'
  } else if (button.action === 'dont-save') {
    result.value = 'Changes discarded'
  }
}

const handleTermsClick = (button) => {
  if (button.action === 'accept') {
    result.value = 'Terms accepted'
  } else if (button.action === 'decline') {
    result.value = 'Terms declined'
  }
}

const handleThreeButtonClick = (button) => {
  result.value = `Action: ${button.action}`
}
</script>
