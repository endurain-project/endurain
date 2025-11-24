<template>
  <h1>{{ $t('healthView.title') }}</h1>
  <div class="row row-gap-3">
    <!-- Include the HealthSideBarComponent -->
    <HealthSideBarComponent
      :activeSection="activeSection"
      @update-active-section="updateActiveSection"
    />

    <LoadingComponent v-if="isLoading" />

    <!-- Include the HealthDashboardZone -->
    <HealthDashboardZone
      :userHealthWeight="userHealthWeight"
      :userHealthSteps="userHealthSteps"
      :userHealthTargets="userHealthTargets"
      v-if="activeSection === 'dashboard' && !isLoading"
    />

    <!-- Include the SettingsUserProfileZone -->
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
      v-if="activeSection === 'weight' && !isLoading"
    />
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
import HealthWeightZone from '../components/Health/HealthWeightZone.vue'
import BackButtonComponent from '@/components/GeneralComponents/BackButtonComponent.vue'
import LoadingComponent from '@/components/GeneralComponents/LoadingComponent.vue'
import { health_weight } from '@/services/health_weightService'
import { health_steps } from '@/services/health_stepsService'
import { health_targets } from '@/services/health_targetsService'
import { useServerSettingsStore } from '@/stores/serverSettingsStore'

const { t } = useI18n()
const serverSettingsStore = useServerSettingsStore()
const activeSection = ref('dashboard')
const isLoading = ref(true)
const isHealthWeightUpdatingLoading = ref(true)
const isHealthStepsUpdatingLoading = ref(true)
const userHealthWeightNumber = ref(0)
const userHealthWeight = ref([])
const userHealthWeightPagination = ref([])
const userHealthStepsNumber = ref(0)
const userHealthSteps = ref([])
const userHealthStepsPagination = ref([])
const userHealthTargets = ref(null)
const pageNumberWeight = ref(1)
const totalPagesWeight = ref(1)
const pageNumberSteps = ref(1)
const totalPagesSteps = ref(1)
const numRecords = serverSettingsStore.serverSettings.num_records_per_page || 25

function updateActiveSection(section) {
  activeSection.value = section
  if (pageNumberWeight.value !== 1 || pageNumberSteps.value !== 1) {
    pageNumberWeight.value = 1
    pageNumberSteps.value = 1
    updateHealthWeight()
    updateHealthSteps()
  }
}

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

async function fetchHealthTargets() {
  try {
    userHealthTargets.value = await health_targets.getUserHealthTargets()
  } catch (error) {
    push.error(`${t('healthView.errorFetchingHealthTargets')} - ${error}`)
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
    }
  }
  for (const data of userHealthWeight.value) {
    if (data.id === editedWeight.id) {
      data.weight = editedWeight.weight
      data.created_at = editedWeight.created_at
    }
  }
}

function setPageNumberWeight(page) {
  pageNumberWeight.value = page
}

watch(pageNumberWeight, updateHealthWeight, { immediate: false })
watch(pageNumberSteps, updateHealthSteps, { immediate: false })

onMounted(async () => {
  await fetchHealthWeight()
  await fetchHealthSteps()
  await fetchHealthTargets()
  isHealthWeightUpdatingLoading.value = false
  isHealthStepsUpdatingLoading.value = false
  isLoading.value = false
})
</script>
