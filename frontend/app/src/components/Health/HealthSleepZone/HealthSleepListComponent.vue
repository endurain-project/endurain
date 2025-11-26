<template>
  <li class="list-group-item p-0 bg-body-tertiary" :class="{ 'shadow rounded p-3': sleepDetails }">
    <div class="d-flex justify-content-between align-items-center">
      <div class="d-flex align-items-center">
        <div>
          <div class="fw-bold">
            <span>{{ formatDuration(data.total_sleep_seconds) }}</span>
          </div>
          <span>
            {{ $t('healthStepsListComponent.labelDate') }}: {{ formatDateShort(data.date) }}
          </span>
        </div>
      </div>
      <div>
        <!-- button toggle sleep details -->
        <a
          class="btn btn-link btn-lg link-body-emphasis"
          data-bs-toggle="collapse"
          :href="`#collapseSleepDetails${data.id}`"
          role="button"
          aria-expanded="false"
          :aria-controls="`collapseSleepDetails${data.id}`"
        >
          <font-awesome-icon :icon="['fas', 'caret-down']" v-if="!sleepDetails" />
          <font-awesome-icon :icon="['fas', 'caret-up']" v-else />
        </a>
        <!-- source logo -->
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
      </div>
    </div>
    <div class="collapse" :id="`collapseSleepDetails${data.id}`">
      <div class="row">
        <div class="col">
          <p>Overall</p>
          <p>Score: {{ data.sleep_score_overall }}</p>
          <p>Quality: {{ data.sleep_score_quality }}</p>
          <p>Duration: {{ formatDuration(data.total_sleep_seconds) }}</p>
        </div>
        <div class="col">
          <p>Stats</p>

        </div>
      </div>
      <HealthSleepTimelineChartComponent
        :data="data.sleep_stages"
      />
    </div>
  </li>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import HealthSleepTimelineChartComponent from './HealthSleepTimelineChartComponent.vue'
// Import constants
import { INTEGRATION_LOGOS } from '@/constants/integrationLogoConstants'
import { formatDuration, formatDateShort } from '@/utils/dateTimeUtils'

const props = defineProps({
  data: {
    type: Object,
    required: true
  }
})

const sleepDetails = ref(false)
console.log(props.data)

onMounted(async () => {
  // Attach Bootstrap collapse event listeners to sync icon state
  const collapseElement = document.getElementById(`collapseSleepDetails${props.data.id}`)
  if (collapseElement) {
    collapseElement.addEventListener('show.bs.collapse', () => {
      sleepDetails.value = true
    })
    collapseElement.addEventListener('hide.bs.collapse', () => {
      sleepDetails.value = false
    })
  }
})
</script>