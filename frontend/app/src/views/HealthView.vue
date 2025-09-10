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
      :userHealthData="userHealthData"
      :userHealthTargets="userHealthTargets"
      v-if="activeSection === 'dashboard' && !isLoading"
    />

    <!-- Include the SettingsUserProfileZone -->
    <HealthWeightZone
      :userHealthData="userHealthData"
      :userHealthDataPagination="userHealthDataPagination"
      :userHealthTargets="userHealthTargets"
      :isLoading="isLoading"
      :totalPages="totalPages"
      :pageNumber="pageNumber"
      @createdWeight="updateWeightListAdded"
      @deletedWeight="updateWeightListDeleted"
      @editedWeight="updateWeightListEdited"
      @pageNumberChanged="setPageNumber"
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
import { health_data } from '@/services/health_dataService'
import { health_targets } from '@/services/health_targetsService'
import { useServerSettingsStore } from '@/stores/serverSettingsStore'

const { t } = useI18n()
const serverSettingsStore = useServerSettingsStore()
const activeSection = ref('dashboard')
const isLoading = ref(true)
const isHealthDataUpdatingLoading = ref(true)
const userHealthDataNumber = ref(0)
const userHealthData = ref([])
const userHealthDataPagination = ref([])
const userHealthTargets = ref(null)
const pageNumber = ref(1)
const totalPages = ref(1)
const numRecords = serverSettingsStore.serverSettings.num_records_per_page || 25

function updateActiveSection(section) {
  activeSection.value = section
  if (pageNumber.value !== 1) {
    pageNumber.value = 1
    updateHealthData()
  }
}

async function updateHealthData() {
  try {
    isHealthDataUpdatingLoading.value = true
    userHealthDataPagination.value = await health_data.getUserHealthDataWithPagination(
      pageNumber.value,
      numRecords
    )
    isHealthDataUpdatingLoading.value = false
  } catch (error) {
    push.error(`${t('healthView.errorFetchingHealthData')} - ${error}`)
  }
}

async function fetchHealthData() {
  try {
    userHealthDataNumber.value = await health_data.getUserHealthDataNumber()
    userHealthData.value = await health_data.getUserHealthData()
    await updateHealthData()
    totalPages.value = Math.ceil(userHealthDataNumber.value / numRecords)
  } catch (error) {
    push.error(`${t('healthView.errorFetchingHealthData')} - ${error}`)
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
  if (userHealthDataPagination.value) {
    updateOrAdd(userHealthDataPagination.value, createdWeight)
  } else {
    userHealthDataPagination.value = [createdWeight]
  }
  if (userHealthData.value) {
    updateOrAdd(userHealthData.value, createdWeight)
  } else {
    userHealthData.value = [createdWeight]
  }
  userHealthDataNumber.value = userHealthData.value.length
}

function updateWeightListDeleted(deletedWeight) {
  for (const data of userHealthDataPagination.value) {
    if (data.id === deletedWeight) {
      data.weight = null
    }
  }
  for (const data of userHealthData.value) {
    if (data.id === deletedWeight) {
      data.weight = null
    }
  }
}

function updateWeightListEdited(editedWeight) {
  for (const data of userHealthDataPagination.value) {
    if (data.id === editedWeight.id) {
      data.weight = editedWeight.weight
      data.created_at = editedWeight.created_at
    }
  }
  for (const data of userHealthData.value) {
    if (data.id === editedWeight.id) {
      data.weight = editedWeight.weight
      data.created_at = editedWeight.created_at
    }
  }
}

function setPageNumber(page) {
  pageNumber.value = page
}

watch(pageNumber, updateHealthData, { immediate: false })

onMounted(async () => {
  await fetchHealthData()
  await fetchHealthTargets()
  isHealthDataUpdatingLoading.value = false
  isLoading.value = false
})
</script>
