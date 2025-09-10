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
          <!-- number field -->
          <label for="selectToEmit"
            ><b>* {{ selectFieldLabel }}</b></label
          >
          <select class="form-select" name="selectToEmit" v-model="optionToEmit" required>
            <option v-for="select in selectOptions" :key="select.id" :value="select.id">
              {{ select.name }}
            </option>
          </select>
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
import { ref } from 'vue'

const props = defineProps({
  modalId: {
    type: String,
    required: true
  },
  title: {
    type: String,
    required: true
  },
  selectFieldLabel: {
    type: String,
    required: true
  },
  selectOptions: {
    type: Array,
    required: true
  },
  selectCurrentOption: {
    type: Number,
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

const emit = defineEmits(['optionToEmitAction'])

const optionToEmit = ref(props.selectCurrentOption)

function submitAction() {
  emit('optionToEmitAction', optionToEmit.value)
}
</script>
