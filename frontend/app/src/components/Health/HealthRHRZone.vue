<template>
  <div class="col">
    <LoadingComponent v-if="isLoading" />
    <div v-else>
      <!-- Checking if userHealthSleep is loaded and has length -->
      <div v-if="userHealthSleep && userHealthSleep.length" class="p-3 bg-body-tertiary rounded shadow-sm">
        <!-- show graph -->
        <HealthRHRLineChartComponent :userHealthSleep="userHealthSleep" :isLoading="isLoading" />

        <br />
        <p>
          {{ $t('healthRHRZoneComponent.labelNumberOfHealthRHR1')
          }}{{ userHealthSleep.length
          }}{{ $t('healthRHRZoneComponent.labelNumberOfHealthRHR2')
          }}{{ userHealthSleepPagination.length
          }}{{ $t('healthRHRZoneComponent.labelNumberOfHealthRHR3') }}
        </p>

        <!-- list zone -->
        <ul class="my-3 list-group list-group-flush" v-for="userHealthSleep in userHealthSleepPagination"
          :key="userHealthSleep.id" :userHealthSleep="userHealthSleep">
          <HealthRHRListComponent :userHealthSleep="userHealthSleep" v-if="userHealthSleep.resting_heart_rate" />
        </ul>

        <!-- pagination area -->
        <PaginationComponent :totalPages="totalPages" :pageNumber="pageNumber" @pageNumberChanged="setPageNumber" />
      </div>
      <!-- Displaying a message or component when there are no RHR measurements -->
      <div v-else>
        <NoItemsFoundComponent />
      </div>
    </div>
  </div>
</template>

<script setup>
import HealthRHRLineChartComponent from './HealthRHRZone/HealthRHRLineChartComponent.vue'
import HealthRHRListComponent from './HealthRHRZone/HealthRHRListComponent.vue'
import LoadingComponent from '../GeneralComponents/LoadingComponent.vue'
import NoItemsFoundComponent from '../GeneralComponents/NoItemsFoundComponents.vue'
import PaginationComponent from '../GeneralComponents/PaginationComponent.vue'

const props = defineProps({
  userHealthSleep: {
    type: [Object, null],
    required: true
  },
  userHealthSleepPagination: {
    type: [Object, null],
    required: true
  },
  isLoading: {
    type: Boolean,
    required: true
  },
  totalPages: {
    type: Number,
    required: true
  },
  pageNumber: {
    type: Number,
    required: true
  }
})

const emit = defineEmits(['pageNumberChanged'])

function setPageNumber(page) {
  emit('pageNumberChanged', page)
}
</script>