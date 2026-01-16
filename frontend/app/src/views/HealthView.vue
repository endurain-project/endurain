<template>
  <h1>{{ $t('healthView.title') }}</h1>
  <div class="row row-gap-3">
    <!-- Include the HealthSideBarComponent -->
    <HealthSideBarComponent
      :activeSection="activeSection"
      @updateActiveSection="updateActiveSection"
    />

    <LoadingComponent v-if="isLoading" />

    <!-- Include the HealthDashboardZone -->
    <HealthDashboardZone
      :userHealthWeight="userHealthWeight"
      :userHealthSteps="userHealthSteps"
      :userHealthSleep="userHealthSleep"
      :userHealthTargets="userHealthTargets"
      v-if="activeSection === 'dashboard' && !isLoading"
    />

    <!-- Include the HealthSleepZone -->
    <HealthSleepZone
      :userHealthSleep="userHealthSleep"
      :userHealthSleepPagination="userHealthSleepPagination"
      :userHealthTargets="userHealthTargets"
      :isLoading="isLoading"
      :totalPages="totalPagesSleep"
      :pageNumber="pageNumberSleep"
      @createdSleep="updateSleepListAdded"
      @editedSleep="updateSleepListEdited"
      @deletedSleep="updateSleepListDeleted"
      @pageNumberChanged="setPageNumberSleep"
      @setSleepTarget="setSleepTarget"
      v-if="activeSection === 'sleep' && !isLoading"
    />

    <!-- Include the HealthRHRZone -->
    <HealthRHRZone
      :userHealthSleep="userHealthSleep"
      :userHealthSleepPagination="userHealthSleepPagination"
      :isLoading="isLoading"
      :totalPages="totalPagesRHR"
      :pageNumber="pageNumberRHR"
      @pageNumberChanged="setPageNumberRHR"
      v-if="activeSection === 'rhr' && !isLoading"
    />

    <!-- Include the HealthStepsZone -->
    <HealthStepsZone
      :userHealthSteps="userHealthSteps"
      :userHealthStepsPagination="userHealthStepsPagination"
      :userHealthTargets="userHealthTargets"
      :isLoading="isLoading"
      :totalPages="totalPagesSteps"
      :pageNumber="pageNumberSteps"
      @createdSteps="updateStepsListAdded"
      @deletedSteps="updateStepsListDeleted"
      @editedSteps="updateStepsListEdited"
      @pageNumberChanged="setPageNumberSteps"
      @setStepsTarget="setStepsTarget"
      v-if="activeSection === 'steps' && !isLoading"
    />

    <!-- Include the HealthWeightZone -->
    <HealthWeightZone
      :userHealthWeight="userHealthWeight"
      :userHealthWeightPagination="userHealthWeightPagination"
      :userHealthTargets="userHealthTargets"
      :isLoading="isLoading"
      :totalPages="totalPagesWeight"
      :pageNumber="pageNumberWeight"
      @createdWeight="updateWeightListAdded"
      @deletedWeight="updateWeightListDeleted"
      @editedWeight="updateWeightListEdited"
      @pageNumberChanged="setPageNumberWeight"
      @setWeightTarget="setWeightTarget"
      v-if="activeSection === 'weight' && !isLoading"
    />
  </div>
  <!-- back button -->
  <BackButtonComponent />
</template>

<script setup>
import { ref, onMounted, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { push } from 'notivue'
import HealthSideBarComponent from '../components/Health/HealthSideBarComponent.vue'
import HealthDashboardZone from '../components/Health/HealthDashboardZoneComponent.vue'
import HealthSleepZone from '../components/Health/HealthSleepZone.vue'
import HealthRHRZone from '@/components/Health/HealthRHRZone.vue'
import HealthStepsZone from '../components/Health/HealthStepsZone.vue'
import HealthWeightZone from '../components/Health/HealthWeightZone.vue'
import BackButtonComponent from '@/components/GeneralComponents/BackButtonComponent.vue'
import LoadingComponent from '@/components/GeneralComponents/LoadingComponent.vue'
import { health_sleep } from '@/services/health_sleepService'
import { health_weight } from '@/services/health_weightService'
import { health_steps } from '@/services/health_stepsService'
import { health_targets } from '@/services/health_targetsService'
import { useServerSettingsStore } from '@/stores/serverSettingsStore'

const route = useRoute()
const router = useRouter()
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
// RHR variables
const pageNumberRHR = ref(1)
const totalPagesRHR = ref(1)
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
  router.push({ query: { tab: section } })
  if (pageNumberWeight.value !== 1 || pageNumberSteps.value !== 1) {
    pageNumberWeight.value = 1
    pageNumberSteps.value = 1
    updateHealthWeightPagination()
    updateHealthStepsPagination()
  }
}

// Sleep functions
async function updateHealthSleepPagination() {
  try {
    isHealthSleepUpdatingLoading.value = true
    const sleepDataPagination = await health_sleep.getUserHealthSleepWithPagination(
      pageNumberSleep.value,
      numRecords
    )
    userHealthSleepPagination.value = sleepDataPagination.records
    isHealthSleepUpdatingLoading.value = false
  } catch (error) {
    push.error(`${t('healthView.errorFetchingHealthSleep')} - ${error}`)
  }
}

async function fetchHealthSleep() {
  try {
    const sleepData = await health_sleep.getUserHealthSleep()
    userHealthSleepNumber.value = sleepData.total
    userHealthSleep.value = sleepData.records
    await updateHealthSleepPagination()
    totalPagesSleep.value = Math.ceil(userHealthSleepNumber.value / numRecords)
  } catch (error) {
    push.error(`${t('healthView.errorFetchingHealthSleep')} - ${error}`)
  }
}

function updateSleepListAdded(createdSleep) {
  const updateOrAdd = (array, newEntry) => {
    const index = array.findIndex((item) => item.id === newEntry.id)
    if (index !== -1) {
      array[index] = newEntry
    } else {
      array.unshift(newEntry)
    }
  }
  if (userHealthSleepPagination.value) {
    updateOrAdd(userHealthSleepPagination.value, createdSleep)
  } else {
    userHealthSleepPagination.value = [createdSleep]
  }
  if (userHealthSleep.value) {
    updateOrAdd(userHealthSleep.value, createdSleep)
  } else {
    userHealthSleep.value = [createdSleep]
  }
  userHealthSleepNumber.value = userHealthSleep.value.length
}

function updateSleepListEdited(editedSleep) {
  const indexPagination = userHealthSleepPagination.value.findIndex(
    (sleep) => sleep.id === editedSleep.id
  )
  const index = userHealthSleep.value.findIndex((sleep) => sleep.id === editedSleep.id)
  userHealthSleepPagination.value[indexPagination] = editedSleep
  userHealthSleep.value[index] = editedSleep
}

function updateSleepListDeleted(deletedSleep) {
  userHealthSleepPagination.value = userHealthSleepPagination.value.filter(
    (sleep) => sleep.id !== deletedSleep
  )
  userHealthSleep.value = userHealthSleep.value.filter((sleep) => sleep.id !== deletedSleep)
  userHealthSleepNumber.value--
}

function setPageNumberSleep(page) {
  pageNumberSleep.value = page
}

// RHR functions
function setPageNumberRHR(page) {
  pageNumberRHR.value = page
}

// Weight functions
async function updateHealthWeightPagination() {
  try {
    isHealthWeightUpdatingLoading.value = true
    const weightDataPagination = await health_weight.getUserHealthWeightWithPagination(
      pageNumberWeight.value,
      numRecords
    )
    userHealthWeightPagination.value = weightDataPagination.records
    isHealthWeightUpdatingLoading.value = false
  } catch (error) {
    push.error(`${t('healthView.errorFetchingHealthWeight')} - ${error}`)
  }
}

async function fetchHealthWeight() {
  try {
    const weightData = await health_weight.getUserHealthWeight()
    userHealthWeight.value = weightData.records
    userHealthWeightNumber.value = weightData.total
    await updateHealthWeightPagination()
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

function updateWeightListEdited(editedWeight) {
  const indexPagination = userHealthWeightPagination.value.findIndex(
    (weight) => weight.id === editedWeight.id
  )
  const index = userHealthWeight.value.findIndex((weight) => weight.id === editedWeight.id)
  userHealthWeightPagination.value[indexPagination] = editedWeight
  userHealthWeight.value[index] = editedWeight
}

function updateWeightListDeleted(deletedWeight) {
  userHealthWeightPagination.value = userHealthWeightPagination.value.filter(
    (weight) => weight.id !== deletedWeight
  )
  userHealthWeight.value = userHealthWeight.value.filter((weight) => weight.id !== deletedWeight)
  userHealthWeightNumber.value--
}

function setPageNumberWeight(page) {
  pageNumberWeight.value = page
}

// Steps functions
async function updateHealthStepsPagination() {
  try {
    isHealthStepsUpdatingLoading.value = true
    const stepsDataPagination = await health_steps.getUserHealthStepsWithPagination(
      pageNumberSteps.value,
      numRecords
    )
    userHealthStepsPagination.value = stepsDataPagination.records
    isHealthStepsUpdatingLoading.value = false
  } catch (error) {
    push.error(`${t('healthView.errorFetchingHealthSteps')} - ${error}`)
  }
}

async function fetchHealthSteps() {
  try {
    const stepsData = await health_steps.getUserHealthSteps()
    userHealthStepsNumber.value = stepsData.total
    userHealthSteps.value = stepsData.records
    await updateHealthStepsPagination()
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

function updateStepsListEdited(editedStep) {
  const indexPagination = userHealthStepsPagination.value.findIndex(
    (step) => step.id === editedStep.id
  )
  const index = userHealthSteps.value.findIndex((step) => step.id === editedStep.id)
  userHealthStepsPagination.value[indexPagination] = editedStep
  userHealthSteps.value[index] = editedStep
}

function updateStepsListDeleted(deletedStep) {
  userHealthStepsPagination.value = userHealthStepsPagination.value.filter(
    (step) => step.id !== deletedStep
  )
  userHealthSteps.value = userHealthSteps.value.filter((step) => step.id !== deletedStep)
  userHealthStepsNumber.value--
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
    weight: weightTarget
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
    steps: stepsTarget
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
    sleep: sleepTarget
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
watch(pageNumberSleep, updateHealthSleepPagination, { immediate: false })
watch(pageNumberSteps, updateHealthStepsPagination, { immediate: false })
watch(pageNumberWeight, updateHealthWeightPagination, { immediate: false })

onMounted(async () => {
  if (route.query.tab && typeof route.query.tab === 'string') {
    activeSection.value = route.query.tab
  }
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
