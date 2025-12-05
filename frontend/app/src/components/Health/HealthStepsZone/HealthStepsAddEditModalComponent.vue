<template>
  <!-- Modal add/edit steps -->
  <div
    class="modal fade"
    :id="action == 'add' ? 'addStepsModal' : action == 'edit' ? editStepsId : ''"
    tabindex="-1"
    :aria-labelledby="action == 'add' ? 'addStepsModal' : action == 'edit' ? editStepsId : ''"
    aria-hidden="true"
  >
    <div class="modal-dialog">
      <div class="modal-content">
        <div class="modal-header">
          <h1 class="modal-title fs-5" id="addStepsModal" v-if="action == 'add'">
            {{ $t('healthStepsAddEditModalComponent.addStepsModalTitle') }}
          </h1>
          <h1 class="modal-title fs-5" :id="editStepsId" v-else>
            {{ $t('healthStepsAddEditModalComponent.editStepsModalTitle') }}
          </h1>
          <button
            type="button"
            class="btn-close"
            data-bs-dismiss="modal"
            aria-label="Close"
          ></button>
        </div>
        <form @submit.prevent="handleSubmit">
          <div class="modal-body">
            <!-- steps fields -->
            <label for="stepsAdd"
              ><b>* {{ $t('healthStepsAddEditModalComponent.addStepsLabel') }}</b></label
            >
            <input
              class="form-control"
              type="number"
              step="0.1"
              name="stepsAdd"
              v-model="newEditSteps"
              required
            />
            <!-- date fields -->
            <label for="stepsDateAdd"
              ><b>* {{ $t('healthStepsAddEditModalComponent.addStepsDateLabel') }}</b></label
            >
            <input
              class="form-control"
              type="date"
              name="stepsDateAdd"
              v-model="newEditStepsDate"
              required
            />

            <p>* {{ $t('generalItems.requiredField') }}</p>
          </div>
          <div class="modal-footer">
            <button type="button" class="btn btn-secondary" data-bs-dismiss="modal">
              {{ $t('generalItems.buttonClose') }}
            </button>
            <button
              type="submit"
              class="btn btn-success"
              data-bs-dismiss="modal"
              v-if="action == 'add'"
            >
              {{ $t('healthStepsAddEditModalComponent.addStepsModalTitle') }}
            </button>
            <button type="submit" class="btn btn-success" data-bs-dismiss="modal" v-else>
              {{ $t('healthStepsAddEditModalComponent.editStepsModalTitle') }}
            </button>
          </div>
        </form>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import { useI18n } from 'vue-i18n'
// Import Notivue push
import { push } from 'notivue'
// Importing the services
import { health_steps } from '@/services/health_stepsService'

const props = defineProps({
  action: {
    type: String,
    required: true
  },
  userHealthStep: {
    type: Object,
    required: false
  }
})

const emit = defineEmits(['isLoadingNewSteps', 'createdSteps', 'editedSteps'])

const { t } = useI18n()
const newEditSteps = ref(5000)
const newEditStepsDate = ref(new Date().toISOString().split('T')[0])
const editStepsId = ref('')

if (props.userHealthStep) {
  newEditSteps.value = props.userHealthStep.steps
  newEditStepsDate.value = props.userHealthStep.date
  editStepsId.value = `editStepsId${props.userHealthStep.id}`
}

async function submitAddSteps() {
  // Set the loading variable to true.
  emit('isLoadingNewSteps', true)
  try {
    // Create the steps data object.
    const data = {
      steps: Number(newEditSteps.value),
      date: newEditStepsDate.value
    }

    const createdSteps = await health_steps.createHealthSteps(data)

    // Set the loading variable to false.
    emit('isLoadingNewSteps', false)

    // Get the created steps and emit it
    emit('createdSteps', createdSteps)

    push.success(t('healthStepsAddEditModalComponent.successAddSteps'))
  } catch (error) {
    // If there is an error, show toast with error message
    // Set the loading variable to false.
    emit('isLoadingNewSteps', false)
    push.error(`${t('healthStepsAddEditModalComponent.errorAddSteps')} - ${error.toString()}`)
  }
}

function submitEditSteps() {
  emit('editedSteps', {
    id: props.userHealthStep.id,
    user_id: props.userHealthStep.user_id,
    steps: newEditSteps.value,
    date: newEditStepsDate.value
  })
}

function handleSubmit() {
  if (props.action === 'add') {
    submitAddSteps()
  } else {
    submitEditSteps()
  }
}
</script>
