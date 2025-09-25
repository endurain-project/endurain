<template>
  <div
    class="modal fade"
    :id="modalId"
    tabindex="-1"
    :aria-labelledby="`${modalId}Label`"
    aria-hidden="true"
  >
    <div class="modal-dialog">
      <div class="modal-content">
        <div class="modal-header">
          <h5 class="modal-title" :id="`${modalId}Label`">{{ title }}</h5>
          <button
            type="button"
            class="btn-close"
            data-bs-dismiss="modal"
            aria-label="Close"
          ></button>
        </div>
        <div class="modal-body">
          <div class="mb-3">
            <label :for="`${modalId}StartDate`" class="form-label">{{
              $t('generalItems.startDateLabel')
            }}</label>
            <input
              type="date"
              class="form-control"
              :id="`${modalId}StartDate`"
              v-model="startDate"
            />
          </div>
          <div class="mb-3">
            <label :for="`${modalId}EndDate`" class="form-label">{{
              $t('generalItems.endDateLabel')
            }}</label>
            <input type="date" class="form-control" :id="`${modalId}EndDate`" v-model="endDate" />
          </div>
        </div>
        <div class="modal-footer">
          <button type="button" class="btn btn-secondary" data-bs-dismiss="modal">
            {{ $t('generalItems.buttonClose') }}
          </button>
          <button
            type="button"
            :class="`btn btn-${actionButtonType}`"
            @click="emitDates"
            data-bs-dismiss="modal"
          >
            {{ actionButtonText }}
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'

const props = defineProps({
  modalId: {
    type: String,
    required: true
  },
  title: {
    type: String,
    required: true
  },
  actionButtonType: {
    type: String,
    default: 'primary'
  },
  actionButtonText: {
    type: String,
    required: true
  }
})

const emit = defineEmits(['datesToEmitAction'])

const { t } = useI18n()
const startDate = ref('')
const endDate = ref('')

const setDefaultDates = () => {
  const today = new Date()
  const sevenDaysAgo = new Date(today)
  sevenDaysAgo.setDate(today.getDate() - 7)

  // Format to YYYY-MM-DD
  startDate.value = sevenDaysAgo.toISOString().split('T')[0]
  endDate.value = today.toISOString().split('T')[0]
}

onMounted(() => {
  setDefaultDates()
})

function emitDates() {
  emit('datesToEmitAction', {
    startDate: startDate.value,
    endDate: endDate.value
  })
}
</script>
