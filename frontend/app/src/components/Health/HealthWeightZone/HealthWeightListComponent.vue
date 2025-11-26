<template>
  <li class="list-group-item d-flex justify-content-between p-0 bg-body-tertiary">
    <div class="d-flex align-items-center">
      <div>
        <div class="fw-bold">
          <span v-if="Number(authStore?.user?.units) === 1"
            >{{ data.weight }} {{ $t('generalItems.unitsKg') }}</span
          >
          <span v-else>{{ kgToLbs(data.weight) }} {{ $t('generalItems.unitsLbs') }}</span>
        </div>
        <span>
          {{ $t('healthWeightListComponent.dateLabel') }}: {{ formatDateShort(data.date) }}
          <span v-if="data.bmi"> | {{ $t('healthWeightListComponent.bmiLabel') }} {{ data.bmi.toFixed(2) }}</span>
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
        :data-bs-target="`#editWeightId${data.id}`"
        ><font-awesome-icon :icon="['fas', 'fa-pen-to-square']"
      /></a>

      <HealthWeightAddEditModalComponent
        :action="'edit'"
        :data="data"
        @editedWeight="updateWeightListEdited"
      />

      <!-- delete weight button -->
      <a
        class="btn btn-link btn-lg link-body-emphasis"
        href="#"
        role="button"
        data-bs-toggle="modal"
        :data-bs-target="`#deleteWeightModal${data.id}`"
        ><font-awesome-icon :icon="['fas', 'fa-trash-can']"
      /></a>

      <ModalComponent
        :modalId="`deleteWeightModal${data.id}`"
        :title="t('healthWeightListComponent.modalDeleteWeightTitle')"
        :body="`${t('healthWeightListComponent.modalDeleteWeightBody')}<b>${data.date}</b>?`"
        :actionButtonType="`danger`"
        :actionButtonText="t('healthWeightListComponent.modalDeleteWeightTitle')"
        @submitAction="submitDeleteWeight"
      />
    </div>
  </li>
</template>

<script setup>
import { useI18n } from 'vue-i18n'
// Importing the stores
import { useAuthStore } from '@/stores/authStore'
// Import Notivue push
import { push } from 'notivue'
// Importing the services
import { health_weight } from '@/services/health_weightService'
// Import the components
import HealthWeightAddEditModalComponent from './HealthWeightAddEditModalComponent.vue'
import ModalComponent from '@/components/Modals/ModalComponent.vue'
// Import constants
import { INTEGRATION_LOGOS } from '@/constants/integrationLogoConstants'

import { formatDateShort } from '@/utils/dateTimeUtils'
import { kgToLbs } from '@/utils/unitsUtils'

const props = defineProps({
  data: {
    type: Object,
    required: true
  }
})

const emit = defineEmits(['editedWeight', 'deletedWeight'])

const { t } = useI18n()
const authStore = useAuthStore()

async function updateWeightListEdited(editedWeight) {
  try {
    await health_weight.editHealthWeight(editedWeight)

    emit('editedWeight', editedWeight)

    push.success(t('healthWeightListComponent.successEditWeight'))
  } catch (error) {
    push.error(`${t('healthWeightListComponent.errorEditWeight')} - ${error.toString()}`)
  }
}

async function submitDeleteWeight() {
  try {
    await health_weight.deleteHealthWeight(props.data.id)

    emit('deletedWeight', props.data.id)

    push.success(t('healthWeightListComponent.successDeleteWeight'))
  } catch (error) {
    push.error(`${t('healthWeightListComponent.errorDeleteWeight')} - ${error.toString()}`)
  }
}
</script>
