<template>
  <div
    class="modal fade"
    :id="modalId"
    tabindex="-1"
    aria-labelledby="confirmModalLabel"
    aria-hidden="true"
    ref="modalRef"
  >
    <div class="modal-dialog">
      <div class="modal-content">
        <div class="modal-header">
          <h5 class="modal-title" id="confirmModalLabel">
            {{ title }}
          </h5>
          <button
            type="button"
            class="btn-close"
            data-bs-dismiss="modal"
            aria-label="Close"
          ></button>
        </div>
        <div class="modal-body">
          <div v-if="typeof content === 'string'" v-html="content"></div>
          <div v-else>
            <slot name="content">
              {{ content }}
            </slot>
          </div>
        </div>
        <div class="modal-footer">
          <button
            v-for="button in buttons"
            :key="button.label"
            type="button"
            :class="button.class || 'btn btn-secondary'"
            @click="handleButtonClick(button)"
          >
            {{ button.label }}
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted, onUnmounted, computed } from 'vue'
import * as b from 'bootstrap'

const props = defineProps({
  title: {
    type: String,
    default: 'Confirm Action'
  },
  content: {
    type: [String, Object],
    default: 'Are you sure you want to proceed?'
  },
  buttons: {
    type: Array,
    default: () => [
      {
        label: 'Cancel',
        class: 'btn btn-secondary',
        action: 'cancel',
        dismiss: true
      },
      {
        label: 'Confirm',
        class: 'btn btn-primary',
        action: 'confirm',
        dismiss: true
      }
    ]
  },
  size: {
    type: String,
    default: 'md', // sm, md, lg, xl
    validator: (value) => ['sm', 'md', 'lg', 'xl'].includes(value)
  },
  backdrop: {
    type: [Boolean, String],
    default: true // true, false, 'static'
  },
  keyboard: {
    type: Boolean,
    default: true
  }
})

const emit = defineEmits(['confirm', 'cancel', 'button-click', 'shown', 'hidden'])

const modalRef = ref(null)
const modalId = ref(`confirm-modal-${Math.random().toString(36).substr(2, 9)}`)

let bootstrapModal = null

const modalClass = computed(() => {
  const classes = ['modal-dialog']
  if (props.size !== 'md') {
    classes.push(`modal-${props.size}`)
  }
  return classes.join(' ')
})

const handleButtonClick = (button) => {
  emit('button-click', button)
  
  // Emit specific events based on action
  if (button.action === 'confirm') {
    emit('confirm', button)
  } else if (button.action === 'cancel') {
    emit('cancel', button)
  }
  
  // Auto-dismiss if specified
  if (button.dismiss) {
    hide()
  }
}

const show = () => {
  if (bootstrapModal) {
    bootstrapModal.show()
  }
}

const hide = () => {
  if (bootstrapModal) {
    bootstrapModal.hide()
  }
}

const toggle = () => {
  if (bootstrapModal) {
    bootstrapModal.toggle()
  }
}

onMounted(() => {
  // Initialize Bootstrap modal
  if (modalRef.value) {
    bootstrapModal = new b.Modal(modalRef.value, {
      backdrop: props.backdrop,
      keyboard: props.keyboard
    })
    
    // Add event listeners
    modalRef.value.addEventListener('shown.bs.modal', () => {
      emit('shown')
    })
    
    modalRef.value.addEventListener('hidden.bs.modal', () => {
      emit('hidden')
    })
  }
})

onUnmounted(() => {
  if (bootstrapModal) {
    bootstrapModal.dispose()
  }
})

// Expose methods to parent component
defineExpose({
  show,
  hide,
  toggle
})
</script>

<style scoped>
.modal-body {
  max-height: 60vh;
  overflow-y: auto;
}
</style>
