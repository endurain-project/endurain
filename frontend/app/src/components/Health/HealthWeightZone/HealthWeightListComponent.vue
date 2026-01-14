<template>
  <li class="list-group-item p-0 bg-body-tertiary" :class="{ 'shadow rounded p-3': weightDetails }">
    <div class="d-flex justify-content-between align-items-center">
      <div class="d-flex align-items-center">
        <div>
          <div class="fw-bold">
            <span v-if="Number(authStore?.user?.units) === 1"
              >{{ userHealthWeight.weight }} {{ $t('generalItems.unitsKg') }}</span
            >
            <span v-else
              >{{ kgToLbs(userHealthWeight.weight) }} {{ $t('generalItems.unitsLbs') }}</span
            >
          </div>
          <span>
            {{ $t('healthWeightListComponent.dateLabel') }}:
            {{ formatDateShort(userHealthWeight.date) }}
          </span>
        </div>
      </div>
      <div>
        <!-- button toggle weight details -->
        <a
          class="btn btn-link btn-lg link-body-emphasis"
          data-bs-toggle="collapse"
          :href="`#collapseWeightDetails${userHealthWeight.id}`"
          role="button"
          aria-expanded="false"
          :aria-controls="`collapseWeightDetails${userHealthWeight.id}`"
          v-if="
            userHealthWeight.bmi ||
            userHealthWeight.body_fat ||
            userHealthWeight.body_water ||
            userHealthWeight.bone_mass ||
            userHealthWeight.muscle_mass
          "
        >
          <font-awesome-icon :icon="['fas', 'caret-down']" v-if="!weightDetails" />
          <font-awesome-icon :icon="['fas', 'caret-up']" v-else />
        </a>
        <!-- source logo -->
        <span
          class="align-middle me-3 d-none d-sm-inline"
          v-if="userHealthWeight.source === 'garmin'"
        >
          <img :src="INTEGRATION_LOGOS.garminConnectApp" alt="Garmin Connect logo" height="22" />
        </span>

        <!-- edit weight button -->
        <a
          class="btn btn-link btn-lg link-body-emphasis"
          href="#"
          role="button"
          data-bs-toggle="modal"
          :data-bs-target="`#editWeightId${userHealthWeight.id}`"
          ><font-awesome-icon :icon="['fas', 'fa-pen-to-square']"
        /></a>

        <HealthWeightAddEditModalComponent
          :action="'edit'"
          :userHealthWeight="userHealthWeight"
          @editedWeight="updateWeightListEdited"
        />

        <!-- delete weight button -->
        <a
          class="btn btn-link btn-lg link-body-emphasis"
          href="#"
          role="button"
          data-bs-toggle="modal"
          :data-bs-target="`#deleteWeightModal${userHealthWeight.id}`"
          ><font-awesome-icon :icon="['fas', 'fa-trash-can']"
        /></a>

        <ModalComponent
          :modalId="`deleteWeightModal${userHealthWeight.id}`"
          :title="t('healthWeightListComponent.modalDeleteWeightTitle')"
          :body="`${t('healthWeightListComponent.modalDeleteWeightBody')}<b>${userHealthWeight.date}</b>?`"
          :actionButtonType="`danger`"
          :actionButtonText="t('healthWeightListComponent.modalDeleteWeightTitle')"
          @submitAction="submitDeleteWeight"
        />
      </div>
    </div>
    <div
      class="collapse"
      :id="`collapseWeightDetails${userHealthWeight.id}`"
      v-if="
        userHealthWeight.bmi ||
        userHealthWeight.body_fat ||
        userHealthWeight.body_water ||
        userHealthWeight.bone_mass ||
        userHealthWeight.muscle_mass
      "
    >
      <!-- Details -->
      <section class="pb-3 mt-3 mb-3">
        <h6 class="fw-semibold mb-2">
          {{ $t('healthWeightListComponent.detailsTitle') }}
        </h6>
        <div class="row">
          <div class="col-12 col-md-6">
            <!-- bmi -->
            <p class="mb-1">
              <span class="fw-semibold"> {{ $t('healthWeightListComponent.bmiLabel') }}: </span>
              <span v-if="userHealthWeight.bmi">{{ userHealthWeight.bmi.toFixed(2) }}</span>
              <span v-else>{{ $t('generalItems.labelNoData') }}</span>
            </p>
            <!-- body_fat -->
            <p class="mb-1">
              <span class="fw-semibold"> {{ $t('healthWeightListComponent.bodyFatLabel') }}: </span>
              <span v-if="userHealthWeight.body_fat"
                >{{ userHealthWeight.body_fat.toFixed(2) }}%</span
              >
              <span v-else>{{ $t('generalItems.labelNoData') }}</span>
            </p>
            <!-- body_water -->
            <p class="mb-1">
              <span class="fw-semibold">
                {{ $t('healthWeightListComponent.bodyWaterLabel') }}:
              </span>
              <span v-if="userHealthWeight.body_water"
                >{{ userHealthWeight.body_water.toFixed(2) }}%</span
              >
              <span v-else>{{ $t('generalItems.labelNoData') }}</span>
            </p>
          </div>
          <div class="col-12 col-md-6">
            <!-- bone_mass -->
            <p class="mb-1">
              <span class="fw-semibold">
                {{ $t('healthWeightListComponent.boneMassLabel') }}:
              </span>
              <span v-if="userHealthWeight.bone_mass && Number(authStore?.user?.units) === 1"
                >{{ userHealthWeight.bone_mass.toFixed(2) }} {{ $t('generalItems.unitsKg') }}</span
              >
              <span v-else-if="userHealthWeight.bone_mass && Number(authStore?.user?.units) === 2"
                >{{ kgToLbs(userHealthWeight.bone_mass) }} {{ $t('generalItems.unitsLbs') }}</span
              >
              <span v-else>{{ $t('generalItems.labelNoData') }}</span>
            </p>
            <!-- muscle_mass -->
            <p class="mb-1">
              <span class="fw-semibold">
                {{ $t('healthWeightListComponent.muscleMassLabel') }}:
              </span>
              <span v-if="userHealthWeight.muscle_mass && Number(authStore?.user?.units) === 1"
                >{{ userHealthWeight.muscle_mass.toFixed(2) }}
                {{ $t('generalItems.unitsKg') }}</span
              >
              <span v-else-if="userHealthWeight.muscle_mass && Number(authStore?.user?.units) === 2"
                >{{ kgToLbs(userHealthWeight.muscle_mass) }} {{ $t('generalItems.unitsLbs') }}</span
              >
              <span v-else>{{ $t('generalItems.labelNoData') }}</span>
            </p>
          </div>
        </div>
      </section>
    </div>
  </li>
</template>

<script setup>
import { ref, onMounted } from 'vue'
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
  userHealthWeight: {
    type: Object,
    required: true
  }
})

const emit = defineEmits(['editedWeight', 'deletedWeight'])

const { t } = useI18n()
const authStore = useAuthStore()
const weightDetails = ref(false)

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
    await health_weight.deleteHealthWeight(props.userHealthWeight.id)

    emit('deletedWeight', props.userHealthWeight.id)

    push.success(t('healthWeightListComponent.successDeleteWeight'))
  } catch (error) {
    push.error(`${t('healthWeightListComponent.errorDeleteWeight')} - ${error.toString()}`)
  }
}

onMounted(async () => {
  // Attach Bootstrap collapse event listeners to sync icon state
  const collapseElement = document.getElementById(
    `collapseWeightDetails${props.userHealthWeight.id}`
  )
  if (collapseElement) {
    collapseElement.addEventListener('show.bs.collapse', () => {
      weightDetails.value = true
    })
    collapseElement.addEventListener('hide.bs.collapse', () => {
      weightDetails.value = false
    })
  }
})
</script>
