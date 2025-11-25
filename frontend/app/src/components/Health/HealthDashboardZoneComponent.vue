<template>
  <div class="col">
    <div class="row">
      <div class="col-lg-4 col-md-12">
        <div class="card mb-3 text-center shadow-sm">
          <div class="card-header">
            <h4>{{ $t('healthDashboardZoneComponent.weight') }}</h4>
          </div>
          <div class="card-body">
            <h1 v-if="currentWeight && Number(authStore?.user?.units) === 1">
              {{ currentWeight }} {{ $t('generalItems.unitsKg') }}
            </h1>
            <h1 v-else-if="currentWeight && authStore.user.units == 2">
              {{ kgToLbs(currentWeight) }} {{ $t('generalItems.unitsLbs') }}
            </h1>
            <h1 v-else>{{ $t('generalItems.labelNotApplicable') }}</h1>
          </div>
          <div class="card-footer text-body-secondary">
            <font-awesome-icon :icon="['fas', 'angle-down']" class="me-1" v-if="currentWeight > userHealthTargets.weight" />
            <font-awesome-icon :icon="['fas', 'angle-up']" class="me-1" v-else/>
            <span v-if="userHealthTargets && userHealthTargets['weight'] && Number(authStore?.user?.units) === 1">
              {{ userHealthTargets.weight }} {{ $t('generalItems.unitsKg') }}
            </span>
            <span v-else-if="userHealthTargets && userHealthTargets['weight'] && Number(authStore?.user?.units) === 2">
              {{ kgToLbs(userHealthTargets.weight) }} {{ $t('generalItems.unitsLbs') }}
            </span>
            <span v-else>{{ $t('healthDashboardZoneComponent.noWeightTarget') }}</span>
          </div>
        </div>
      </div>
      <div class="col-lg-4 col-md-12">
        <div class="card mb-3 text-center shadow-sm">
          <div class="card-header">
            <h4>{{ $t('healthDashboardZoneComponent.bmi') }}</h4>
          </div>
          <div class="card-body">
            <h1 v-if="currentBMI">{{ currentBMI }}</h1>
            <h1 v-else>{{ $t('generalItems.labelNotApplicable') }}</h1>
          </div>
          <div class="card-footer text-body-secondary">
            <span v-if="currentBMI">{{ bmiDescription }}</span>
            <span v-else-if="!currentBMI && currentWeight">{{
              $t('healthDashboardZoneComponent.noHeightDefined')
            }}</span>
            <span v-else>{{ $t('healthDashboardZoneComponent.noWeightData') }}</span>
          </div>
        </div>
      </div>
      <div class="col-lg-4 col-md-12">
        <div class="card mb-3 text-center shadow-sm">
          <div class="card-header">
            <h4>{{ $t('healthDashboardZoneComponent.steps') }}</h4>
          </div>
          <div class="card-body">
            <h1 v-if="todaySteps">{{ todaySteps }}</h1>
            <h1 v-else>{{ $t('generalItems.labelNotApplicable') }}</h1>
          </div>
          <div class="card-footer text-body-secondary">
            <span v-if="userHealthTargets && userHealthTargets['steps']">
              <font-awesome-icon :icon="['fas', 'angle-down']" class="me-1" v-if="todaySteps < userHealthTargets.steps" />
              <font-awesome-icon :icon="['fas', 'angle-up']" class="me-1" v-else/>
              {{ userHealthTargets.steps }} {{ $t('healthDashboardZoneComponent.stepsTargetLabel') }}
            </span>
            <span v-else>{{ $t('healthDashboardZoneComponent.noStepsTarget') }}</span>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
// Importing the stores
import { useAuthStore } from '@/stores/authStore'
import { kgToLbs } from '@/utils/unitsUtils'

const props = defineProps({
  userHealthWeight: {
    type: [Object, null],
    required: true
  },
  userHealthSteps: {
    type: [Object, null],
    required: true
  },
  userHealthTargets: {
    type: [Object, null],
    required: true
  }
})

const { t } = useI18n()
const authStore = useAuthStore()
const currentWeight = ref(null)
const currentBMI = ref(null)
const bmiDescription = ref(null)
const todaySteps = ref(null)

onMounted(async () => {
  if (props.userHealthWeight) {
    for (const data of props.userHealthWeight) {
      if (data.weight) {
        currentWeight.value = data.weight
        currentBMI.value = data.bmi ? data.bmi.toFixed(2) : null
        break
      }
    }

    if (currentBMI.value) {
      if (currentBMI.value < 18.5) {
        bmiDescription.value = t('healthDashboardZoneComponent.bmiUnderweight')
      } else if (currentBMI.value >= 18.5 && currentBMI.value < 24.9) {
        bmiDescription.value = t('healthDashboardZoneComponent.bmiNormalWeight')
      } else if (currentBMI.value >= 25 && currentBMI.value < 29.9) {
        bmiDescription.value = t('healthDashboardZoneComponent.bmiOverweight')
      } else if (currentBMI.value >= 30 && currentBMI.value < 34.9) {
        bmiDescription.value = t('healthDashboardZoneComponent.bmiObesityClass1')
      } else if (currentBMI.value >= 35 && currentBMI.value < 39.9) {
        bmiDescription.value = t('healthDashboardZoneComponent.bmiObesityClass2')
      } else if (currentBMI.value >= 40) {
        bmiDescription.value = t('healthDashboardZoneComponent.bmiObesityClass3')
      }
    }
  }
  if (props.userHealthSteps) {
    for (const data of props.userHealthSteps) {
      if (data.steps) {
        todaySteps.value = data.steps
        break
      }
    }
  }
})
</script>