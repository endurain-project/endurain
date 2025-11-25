<template>
  <li class="list-group-item d-flex justify-content-between p-0 bg-body-tertiary">
    <div class="d-flex align-items-center">
      <div>
        <div class="fw-bold">
          <span>{{ data.steps }} {{ $t('healthStepsListComponent.labelSteps') }}</span
          >
        </div>
        <span>
          Date: {{ formatDateShort(data.date) }}
        </span>
      </div>
    </div>
    <div>
      <span
        class="align-middle me-3 d-none d-sm-inline"
        v-if="data.source === 'garmin'"
      >
        <img
          :src="INTEGRATION_LOGOS.garminConnectApp"
          alt="Garmin Connect logo"
          height="22"
        />
      </span>

      <!-- edit weight button -->
      <a
        class="btn btn-link btn-lg link-body-emphasis"
        href="#"
        role="button"
        data-bs-toggle="modal"
        :data-bs-target="`#editStepsId${data.id}`"
        ><font-awesome-icon :icon="['fas', 'fa-pen-to-square']"
      /></a>

      <HealthStepsAddEditModalComponent
        :action="'edit'"
        :data="data"
        @editedSteps="updateStepsListEdited"
      />

      <!-- delete weight button -->
      <a
        class="btn btn-link btn-lg link-body-emphasis"
        href="#"
        role="button"
        data-bs-toggle="modal"
        :data-bs-target="`#deleteStepsModal${data.id}`"
        ><font-awesome-icon :icon="['fas', 'fa-trash-can']"
      /></a>

      <ModalComponent
        :modalId="`deleteStepsModal${data.id}`"
        :title="t('healthStepsListComponent.modalDeleteStepsTitle')"
        :body="`${t('healthStepsListComponent.modalDeleteStepsBody')}<b>${data.date}</b>?`"
        :actionButtonType="`danger`"
        :actionButtonText="t('healthStepsListComponent.modalDeleteStepsTitle')"
        @submitAction="submitDeleteSteps"
      />
    </div>
  </li>
</template>

<script setup>
import { useI18n } from 'vue-i18n'
// Import Notivue push
import { push } from 'notivue'
// Importing the services
import { health_steps } from '@/services/health_stepsService'
// Import the components
import HealthStepsAddEditModalComponent from './HealthStepsAddEditModalComponent.vue'
import ModalComponent from '@/components/Modals/ModalComponent.vue'
// Import constants
import { INTEGRATION_LOGOS } from '@/constants/integrationLogoConstants'

import { formatDateShort } from '@/utils/dateTimeUtils'

const props = defineProps({
  data: {
    type: Object,
    required: true
  }
})

const emit = defineEmits(['editedSteps', 'deletedSteps'])

const { t } = useI18n()

async function updateStepsListEdited(editedSteps) {
  try {
    await health_steps.editHealthSteps(editedSteps)

    emit('editedSteps', editedSteps)

    push.success(t('healthStepsListComponent.successEditSteps'))
  } catch (error) {
    push.error(`${t('healthStepsListComponent.errorEditSteps')} - ${error.toString()}`)
  }
}

async function submitDeleteSteps() {
  try {
    await health_steps.deleteHealthSteps(props.data.id)

    emit('deletedSteps', props.data.id)

    push.success(t('healthStepsListComponent.successDeleteSteps'))
  } catch (error) {
    push.error(`${t('healthStepsListComponent.errorDeleteSteps')} - ${error.toString()}`)
  }
}
</script>
