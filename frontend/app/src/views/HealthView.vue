<template>
  <h1>{{ $t('healthView.title') }}</h1>
  <div class="row row-gap-3">
    <!-- Include the HealthSideBarComponent -->
    <HealthSideBarComponent :activeSection="activeSection" @update-active-section="updateActiveSection" />

    <LoadingComponent v-if="isLoading" />

    <!-- Include the HealthDashboardZone -->
    <HealthDashboardZone :userHealthWeight="userHealthWeight" :userHealthSteps="userHealthSteps"
      :userHealthSleep="userHealthSleep" :userHealthTargets="userHealthTargets"
      v-if="activeSection === 'dashboard' && !isLoading" />

    <!-- Include the HealthWeightZone -->
    <HealthWeightZone :userHealthWeight="userHealthWeight" :userHealthWeightPagination="userHealthWeightPagination"
      :userHealthTargets="userHealthTargets" :isLoading="isLoading" :totalPages="totalPagesWeight"
      :pageNumber="pageNumberWeight" @createdWeight="updateWeightListAdded" @deletedWeight="updateWeightListDeleted"
      @editedWeight="updateWeightListEdited" @pageNumberChanged="setPageNumberWeight" @setWeightTarget="setWeightTarget"
      v-if="activeSection === 'weight' && !isLoading" />

    <!-- Include the HealthStepsZone -->
    <HealthStepsZone :userHealthSteps="userHealthSteps" :userHealthStepsPagination="userHealthStepsPagination"
      :userHealthTargets="userHealthTargets" :isLoading="isLoading" :totalPages="totalPagesSteps"
      :pageNumber="pageNumberSteps" @createdSteps="updateStepsListAdded" @deletedSteps="updateStepsListDeleted"
      @editedSteps="updateStepsListEdited" @pageNumberChanged="setPageNumberSteps" @setStepsTarget="setStepsTarget"
      v-if="activeSection === 'steps' && !isLoading" />

    <!-- Include the HealthSleepZone -->
    <HealthSleepZone :userHealthSleep="userHealthSleep" :userHealthSleepPagination="userHealthSleepPagination"
      :userHealthTargets="userHealthTargets" :isLoading="isLoading" :totalPages="totalPagesSleep"
      :pageNumber="pageNumberSleep" @pageNumberChanged="setPageNumberSleep" @setSleepTarget="setSleepTarget"
      v-if="activeSection === 'sleep' && !isLoading" />
  </div>
  <!-- back button -->
  <BackButtonComponent />
</template>

<script setup>
import { ref, onMounted, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { push } from 'notivue'
import HealthSideBarComponent from '../components/Health/HealthSideBarComponent.vue'
import HealthDashboardZone from '../components/Health/HealthDashboardZoneComponent.vue'
import HealthSleepZone from '../components/Health/HealthSleepZone.vue'
import HealthStepsZone from '../components/Health/HealthStepsZone.vue'
import HealthWeightZone from '../components/Health/HealthWeightZone.vue'
import BackButtonComponent from '@/components/GeneralComponents/BackButtonComponent.vue'
import LoadingComponent from '@/components/GeneralComponents/LoadingComponent.vue'
import { health_sleep } from '@/services/health_sleepService'
import { health_weight } from '@/services/health_weightService'
import { health_steps } from '@/services/health_stepsService'
import { health_targets } from '@/services/health_targetsService'
import { useServerSettingsStore } from '@/stores/serverSettingsStore'

const { t } = useI18n()
const serverSettingsStore = useServerSettingsStore()
const activeSection = ref('dashboard')
const isLoading = ref(true)
const numRecords = serverSettingsStore.serverSettings.num_records_per_page || 25
// Sleep variables
const isHealthSleepUpdatingLoading = ref(true)
const userHealthSleepNumber = ref(0)
const userHealthSleep = ref([])
const userHealthSleepPagination = ref([])
const pageNumberSleep = ref(1)
const totalPagesSleep = ref(1)
// Weight variables
const isHealthWeightUpdatingLoading = ref(true)
const userHealthWeightNumber = ref(0)
const userHealthWeight = ref([])
const userHealthWeightPagination = ref([])
const pageNumberWeight = ref(1)
const totalPagesWeight = ref(1)
// Steps variables
const isHealthStepsUpdatingLoading = ref(true)
const userHealthStepsNumber = ref(0)
const userHealthSteps = ref([])
const userHealthStepsPagination = ref([])
const pageNumberSteps = ref(1)
const totalPagesSteps = ref(1)
// Targets variables
const userHealthTargets = ref(null)

function updateActiveSection(section) {
  activeSection.value = section
  if (pageNumberWeight.value !== 1 || pageNumberSteps.value !== 1) {
    pageNumberWeight.value = 1
    pageNumberSteps.value = 1
    updateHealthWeight()
    updateHealthSteps()
  }
}

// Sleep functions
async function updateHealthSleep() {
  try {
    isHealthSleepUpdatingLoading.value = true
    userHealthSleepPagination.value = await health_sleep.getUserHealthSleepWithPagination(
      pageNumberSleep.value,
      numRecords
    )
    isHealthSleepUpdatingLoading.value = false
  } catch (error) {
    push.error(`${t('healthView.errorFetchingHealthSleep')} - ${error}`)
  }
}

async function fetchHealthSleep() {
  try {
    userHealthSleepNumber.value = await health_sleep.getUserHealthSleepNumber()
    userHealthSleep.value = await health_sleep.getUserHealthSleep()
    await updateHealthSleep()
    totalPagesSleep.value = Math.ceil(userHealthSleepNumber.value / numRecords)
  } catch (error) {
    push.error(`${t('healthView.errorFetchingHealthSleep')} - ${error}`)
  }
}

function setPageNumberSleep(page) {
  pageNumberSleep.value = page
}

// Weight functions
async function updateHealthWeight() {
  try {
    isHealthWeightUpdatingLoading.value = true
    userHealthWeightPagination.value = await health_weight.getUserHealthWeightWithPagination(
      pageNumberWeight.value,
      numRecords
    )
    isHealthWeightUpdatingLoading.value = false
  } catch (error) {
    push.error(`${t('healthView.errorFetchingHealthWeight')} - ${error}`)
  }
}

async function fetchHealthWeight() {
  try {
    userHealthWeightNumber.value = await health_weight.getUserHealthWeightNumber()
    userHealthWeight.value = await health_weight.getUserHealthWeight()
    await updateHealthWeight()
    totalPagesWeight.value = Math.ceil(userHealthWeightNumber.value / numRecords)
  } catch (error) {
    push.error(`${t('healthView.errorFetchingHealthWeight')} - ${error}`)
  }
}

function updateWeightListAdded(createdWeight) {
  const updateOrAdd = (array, newEntry) => {
    const index = array.findIndex((item) => item.id === newEntry.id)
    if (index !== -1) {
      array[index] = newEntry
    } else {
      array.unshift(newEntry)
    }
  }
  if (userHealthWeightPagination.value) {
    updateOrAdd(userHealthWeightPagination.value, createdWeight)
  } else {
    userHealthWeightPagination.value = [createdWeight]
  }
  if (userHealthWeight.value) {
    updateOrAdd(userHealthWeight.value, createdWeight)
  } else {
    userHealthWeight.value = [createdWeight]
  }
  userHealthWeightNumber.value = userHealthWeight.value.length
}

function updateWeightListDeleted(deletedWeight) {
  for (const data of userHealthWeightPagination.value) {
    if (data.id === deletedWeight) {
      data.weight = null
    }
  }
  for (const data of userHealthWeight.value) {
    if (data.id === deletedWeight) {
      data.weight = null
    }
  }
}

function updateWeightListEdited(editedWeight) {
  for (const data of userHealthWeightPagination.value) {
    if (data.id === editedWeight.id) {
      data.weight = editedWeight.weight
      data.created_at = editedWeight.created_at
      data.bmi = editedWeight.bmi
      data.body_fat = editedWeight.body_fat
      data.body_water = editedWeight.body_water
      data.bone_mass = editedWeight.bone_mass
      data.muscle_mass = editedWeight.muscle_mass
    }
  }
  for (const data of userHealthWeight.value) {
    if (data.id === editedWeight.id) {
      data.weight = editedWeight.weight
      data.created_at = editedWeight.created_at
      data.bmi = editedWeight.bmi
      data.body_fat = editedWeight.body_fat
      data.body_water = editedWeight.body_water
      data.bone_mass = editedWeight.bone_mass
      data.muscle_mass = editedWeight.muscle_mass
    }
  }
}

function setPageNumberWeight(page) {
  pageNumberWeight.value = page
}

// Steps functions
async function updateHealthSteps() {
  try {
    isHealthStepsUpdatingLoading.value = true
    userHealthStepsPagination.value = await health_steps.getUserHealthStepsWithPagination(
      pageNumberSteps.value,
      numRecords
    )
    isHealthStepsUpdatingLoading.value = false
  } catch (error) {
    push.error(`${t('healthView.errorFetchingHealthSteps')} - ${error}`)
  }
}

async function fetchHealthSteps() {
  try {
    userHealthStepsNumber.value = await health_steps.getUserHealthStepsNumber()
    userHealthSteps.value = await health_steps.getUserHealthSteps()
    await updateHealthSteps()
    totalPagesSteps.value = Math.ceil(userHealthStepsNumber.value / numRecords)
  } catch (error) {
    push.error(`${t('healthView.errorFetchingHealthSteps')} - ${error}`)
  }
}

function updateStepsListAdded(createdStep) {
  const updateOrAdd = (array, newEntry) => {
    const index = array.findIndex((item) => item.id === newEntry.id)
    if (index !== -1) {
      array[index] = newEntry
    } else {
      array.unshift(newEntry)
    }
  }
  if (userHealthStepsPagination.value) {
    updateOrAdd(userHealthStepsPagination.value, createdStep)
  } else {
    userHealthStepsPagination.value = [createdStep]
  }
  if (userHealthSteps.value) {
    updateOrAdd(userHealthSteps.value, createdStep)
  } else {
    userHealthSteps.value = [createdStep]
  }
  userHealthStepsNumber.value = userHealthSteps.value.length
}

function updateStepsListDeleted(deletedStep) {
  for (const data of userHealthStepsPagination.value) {
    if (data.id === deletedStep) {
      data.steps = null
    }
  }
  for (const data of userHealthSteps.value) {
    if (data.id === deletedStep) {
      data.steps = null
    }
  }
}

function updateStepsListEdited(editedStep) {
  for (const data of userHealthStepsPagination.value) {
    if (data.id === editedStep.id) {
      data.steps = editedStep.steps
      data.created_at = editedStep.created_at
    }
  }
  for (const data of userHealthSteps.value) {
    if (data.id === editedStep.id) {
      data.steps = editedStep.steps
      data.created_at = editedStep.created_at
    }
  }
}

function setPageNumberSteps(page) {
  pageNumberSteps.value = page
}

// Health Targets functions
async function fetchHealthTargets() {
  try {
    userHealthTargets.value = await health_targets.getUserHealthTargets()
  } catch (error) {
    push.error(`${t('healthView.errorFetchingHealthTargets')} - ${error}`)
  }
}

function setWeightTarget(weightTarget) {
  const data = {
    id: userHealthTargets.value.id,
    user_id: userHealthTargets.value.user_id,
    weight: weightTarget,
  }
  try {
    health_targets.setUserHealthTargets(data)
    userHealthTargets.value.weight = weightTarget
    push.success(t('healthView.successUpdatingWeightTarget'))
  } catch (error) {
    push.error(`${t('healthView.errorUpdatingWeightTarget')} - ${error}`)
  }
}

function setStepsTarget(stepsTarget) {
  const data = {
    id: userHealthTargets.value.id,
    user_id: userHealthTargets.value.user_id,
    steps: stepsTarget,
  }
  try {
    health_targets.setUserHealthTargets(data)
    userHealthTargets.value.steps = stepsTarget
    push.success(t('healthView.successUpdatingStepsTarget'))
  } catch (error) {
    push.error(`${t('healthView.errorUpdatingStepsTarget')} - ${error}`)
  }
}

function setSleepTarget(sleepTarget) {
  const data = {
    id: userHealthTargets.value.id,
    user_id: userHealthTargets.value.user_id,
    sleep: sleepTarget,
  }
  try {
    health_targets.setUserHealthTargets(data)
    userHealthTargets.value.sleep = sleepTarget
    push.success(t('healthView.successUpdatingSleepTarget'))
  } catch (error) {
    push.error(`${t('healthView.errorUpdatingSleepTarget')} - ${error}`)
  }
}

// Watch functions
watch(pageNumberSleep, updateHealthSleep, { immediate: false })
watch(pageNumberSteps, updateHealthSteps, { immediate: false })
watch(pageNumberWeight, updateHealthWeight, { immediate: false })

onMounted(async () => {
  await fetchHealthSleep()
  await fetchHealthSteps()
  await fetchHealthWeight()
  await fetchHealthTargets()
  isHealthSleepUpdatingLoading.value = false
  isHealthStepsUpdatingLoading.value = false
  isHealthWeightUpdatingLoading.value = false
  isLoading.value = false
})
</script>
