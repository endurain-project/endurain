<template>
  <div class="col">
    <LoadingComponent v-if="isLoading" />
    <div v-else>
      <!-- add sleep button -->
      <div class="d-flex">
        <a class="w-100 btn btn-primary shadow-sm me-1 disabled" href="#" role="button" data-bs-toggle="modal"
          data-bs-target="#addSleepModal">{{ t('healthSleepZoneComponent.buttonAddSleep') }}</a>
        <a class="w-100 btn btn-primary shadow-sm ms-1" href="#" role="button" data-bs-toggle="modal"
          data-bs-target="#addSleepTargetModal">{{ $t('healthSleepZoneComponent.buttonSleepTarget') }}</a>
      </div>

      <!--<HealthStepsAddEditModalComponent
        :action="'add'"
        @isLoadingNewSteps="updateIsLoadingNewSteps"
        @createdSteps="updateStepsListAdded"
      />-->

      <ModalComponentHoursMinutesInput modalId="addSleepTargetModal"
        :title="t('healthSleepZoneComponent.buttonSleepTarget')"
        :hoursFieldLabel="t('healthSleepZoneComponent.modalSleepTargetHoursLabel')"
        :minutesFieldLabel="t('healthSleepZoneComponent.modalSleepTargetMinutesLabel')" actionButtonType="success"
        :actionButtonText="t('generalItems.buttonSubmit')"
        :secondsDefaultValue="props.userHealthTargets?.sleep || 28800" @fieldsToEmitAction="submitSetSleepTarget" />

      <!-- Checking if userHealthSleepPagination is loaded and has length -->
      <div v-if="userHealthSleepPagination && userHealthSleepPagination.length"
        class="mt-3 p-3 bg-body-tertiary rounded shadow-sm">
        <!-- show graph -->
        <HealthSleepBarChartComponent :userHealthTargets="userHealthTargets" :userHealthSleep="userHealthSleep"
          :isLoading="isLoading" />

        <br />
        <p>
          {{ $t('healthSleepZoneComponent.labelNumberOfHealthSleep1')
          }}{{ userHealthSleep.length
          }}{{ $t('healthSleepZoneComponent.labelNumberOfHealthSleep2')
          }}{{ userHealthSleepPagination.length
          }}{{ $t('healthSleepZoneComponent.labelNumberOfHealthSleep3') }}
        </p>

        <!-- Displaying loading new sleep if applicable -->
        <ul class="mt-3 list-group list-group-flush" v-if="isLoadingNewSleep">
          <li class="list-group-item rounded">
            <LoadingComponent />
          </li>
        </ul>

        <!-- list zone -->
        <ul class="my-3 list-group list-group-flush" v-for="data in userHealthSleepPagination" :key="data.id"
          :data="data">
          <!--<HealthSleepTimelineChartComponent
            :data="data.sleep_stages"
          />-->
          <HealthSleepListComponent :userHealthSleep="data" />
        </ul>

        <!-- pagination area -->
        <PaginationComponent :totalPages="totalPages" :pageNumber="pageNumber" @pageNumberChanged="setPageNumber" />
      </div>
      <!-- Displaying a message or component when there are no weight measurements -->
      <div v-else class="mt-3">
        <br />
        <NoItemsFoundComponent />
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import { useI18n } from 'vue-i18n'

import ModalComponentHoursMinutesInput from '../Modals/ModalComponentHoursMinutesInput.vue'
import HealthSleepBarChartComponent from './HealthSleepZone/HealthSleepBarChartComponent.vue'
import HealthSleepListComponent from './HealthSleepZone/HealthSleepListComponent.vue'
import HealthSleepTimelineChartComponent from './HealthSleepZone/HealthSleepTimelineChartComponent.vue'
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
  userHealthTargets: {
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

const { t } = useI18n()
const isLoadingNewSleep = ref(false)

function setPageNumber(page) {
  emit('pageNumberChanged', page)
}

function submitSetSleepTarget(sleepTarget) {
  emit('setSleepTarget', sleepTarget)
}
</script>