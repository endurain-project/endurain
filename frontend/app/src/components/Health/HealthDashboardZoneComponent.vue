<template>
  <div class="col">
    <div class="row">
      <!-- Today's sleep -->
      <div class="col-lg-4 col-md-12">
        <div class="card mb-3 text-center shadow-sm">
          <div class="card-header">
            <h4>{{ $t('healthDashboardZoneComponent.sleep') }}</h4>
          </div>
          <div class="card-body">
            <h1 v-if="todaySleep">{{ formatDuration(todaySleep) }}</h1>
            <h1 v-else>{{ $t('generalItems.labelNoData') }}</h1>
          </div>
          <div class="card-footer text-body-secondary">
            <span v-if="userHealthTargets && userHealthTargets['sleep']">
              <font-awesome-icon
                :icon="['fas', 'angle-down']"
                class="me-1"
                v-if="todaySleep < userHealthTargets.sleep"
              />
              <font-awesome-icon :icon="['fas', 'angle-up']" class="me-1" v-else />
              {{ formatDuration(userHealthTargets.sleep) }}
            </span>
            <span v-else>{{ $t('healthDashboardZoneComponent.noSleepTarget') }}</span>
          </div>
        </div>
      </div>
      <!-- resting heart rate -->
      <div class="col-lg-4 col-md-12">
        <div class="card mb-3 text-center shadow-sm">
          <div class="card-header">
            <h4>{{ $t('healthDashboardZoneComponent.restingHeartRate') }}</h4>
          </div>
          <div class="card-body">
            <h1 v-if="restingHeartRate">
              {{ restingHeartRate }} {{ $t('generalItems.unitsBpm') }}
            </h1>
            <h1 v-else>{{ $t('generalItems.labelNoData') }}</h1>
          </div>
          <div class="card-footer text-body-secondary">
            <span v-if="hrvStatus">{{ $t(getHrvStatusI18nKey(hrvStatus)) }}</span>
            <span v-else>{{ $t('generalItems.labelNoData') }}</span>
          </div>
        </div>
      </div>
      <!-- avg skin temperature deviation -->
      <div class="col-lg-4 col-md-12">
        <div class="card mb-3 text-center shadow-sm">
          <div class="card-header">
            <h4>{{ $t('healthDashboardZoneComponent.avgSkinTemperatureDeviation') }}</h4>
          </div>
          <div class="card-body">
            <h1 v-if="avgSkinTempDeviation">
              {{ avgSkinTempDeviation }} {{ $t('generalItems.unitsCelsius') }}
            </h1>
            <h1 v-else>{{ $t('generalItems.labelNoData') }}</h1>
          </div>
          <div class="card-footer text-body-secondary">
            <span>{{ $t('generalItems.labelNoData') }}</span>
          </div>
        </div>
      </div>
      <!-- weight -->
      <div class="col-lg-4 col-md-12">
        <div class="card mb-3 text-center shadow-sm">
          <div class="card-header">
            <h4>{{ $t('healthDashboardZoneComponent.weight') }}</h4>
          </div>
          <div class="card-body">
            <h1 v-if="currentWeight && authStore?.user?.units === 'metric'">
              {{ currentWeight }} {{ $t('generalItems.unitsKg') }}
            </h1>
            <h1 v-else-if="currentWeight && authStore.user.units === 'imperial'">
              {{ kgToLbs(currentWeight) }} {{ $t('generalItems.unitsLbs') }}
            </h1>
            <h1 v-else>{{ $t('generalItems.labelNotApplicable') }}</h1>
          </div>
          <div class="card-footer text-body-secondary">
            <font-awesome-icon
              :icon="['fas', 'angle-down']"
              class="me-1"
              v-if="currentWeight > userHealthTargets.weight"
            />
            <font-awesome-icon :icon="['fas', 'angle-up']" class="me-1" v-else />
            <span
              v-if="
                userHealthTargets &&
                userHealthTargets['weight'] &&
                authStore?.user?.units === 'metric'
              "
            >
              {{ userHealthTargets.weight }} {{ $t('generalItems.unitsKg') }}
            </span>
            <span
              v-else-if="
                userHealthTargets &&
                userHealthTargets['weight'] &&
                authStore?.user?.units === 'imperial'
              "
            >
              {{ kgToLbs(userHealthTargets.weight) }} {{ $t('generalItems.unitsLbs') }}
            </span>
            <span v-else>{{ $t('healthDashboardZoneComponent.noWeightTarget') }}</span>
          </div>
        </div>
      </div>
      <!-- BMI -->
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
      <!-- Today's steps -->
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
              <font-awesome-icon
                :icon="['fas', 'angle-down']"
                class="me-1"
                v-if="todaySteps < userHealthTargets.steps"
              />
              <font-awesome-icon :icon="['fas', 'angle-up']" class="me-1" v-else />
              {{ userHealthTargets.steps }}
              {{ $t('healthDashboardZoneComponent.stepsTargetLabel') }}
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
import { formatDuration } from '@/utils/dateTimeUtils'
import { getHrvStatusI18nKey } from '@/utils/healthUtils'

const props = defineProps({
  userHealthWeight: {
    type: [Object, null],
    required: true
  },
  userHealthSteps: {
    type: [Object, null],
    required: true
  },
  userHealthSleep: {
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
const todaySleep = ref(null)
const restingHeartRate = ref(null)
const hrvStatus = ref(null)
const avgSkinTempDeviation = ref(null)

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
  if (props.userHealthSleep) {
    for (const data of props.userHealthSleep) {
      if (data.total_sleep_seconds) {
        todaySleep.value = data.total_sleep_seconds
        restingHeartRate.value = data.resting_heart_rate
        hrvStatus.value = data.hrv_status
        avgSkinTempDeviation.value = data.avg_skin_temp_deviation
        break
      }
    }
  }
})
</script>
