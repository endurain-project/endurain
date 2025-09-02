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
          <!-- file field -->
          <label for="fileToEmit"
            ><b>* {{ fileFieldLabel }}</b></label
          >
          <input
            class="form-control"
            type="file"
            name="fileToEmit"
            :placeholder="`${fileFieldLabel}`"
            :accept="filesAccepted"
            required
          />
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
const props = defineProps({
  modalId: {
    type: String,
    required: true
  },
  title: {
    type: String,
    required: true
  },
  fileFieldLabel: {
    type: String,
    required: true
  },
  filesAccepted: {
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
  }
})

const emit = defineEmits(['fileToEmitAction'])

function submitAction() {
  const fileInput = document.querySelector(`#${props.modalId} input[name="fileToEmit"]`)
  const file = fileInput?.files[0]
  if (file) {
    emit('fileToEmitAction', file)
    fileInput.value = ''
  }
}
</script>
