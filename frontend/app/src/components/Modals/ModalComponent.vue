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
          <span v-html="body"></span>
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
            data-bs-dismiss="modal"
            >{{ actionButtonText }}</a
          >
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
// Define props
const props = defineProps({
  modalId: {
    type: String,
    required: true
  },
  title: {
    type: String,
    required: true
  },
  body: {
    type: String,
    required: true
  },
  actionButtonType: {
    type: String,
    required: true
  },
  actionButtonText: {
    type: String,
    required: true
  },
  valueToEmit: {
    type: [Number, String],
    default: null
  },
  emitValue: {
    type: Boolean,
    default: false
  }
})

// Define emits
const emit = defineEmits(['submitAction'])

// Methods
function submitAction() {
  if (props.emitValue) {
    emit('submitAction', props.valueToEmit)
  } else {
    emit('submitAction', true)
  }
}
</script>
