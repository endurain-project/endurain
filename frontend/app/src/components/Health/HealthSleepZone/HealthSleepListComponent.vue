<template>
  <li class="list-group-item p-0 bg-body-tertiary" :class="{ 'shadow rounded p-3': sleepDetails }">
    <div class="d-flex justify-content-between align-items-center">
      <div class="d-flex align-items-center">
        <div>
          <div class="fw-bold">
            <span>{{ formatDuration(userHealthSleep.total_sleep_seconds) }}</span>
          </div>
          <span>
            {{ $t('healthSleepListComponent.labelDate') }}:
            {{ formatDateShort(userHealthSleep.date) }}
          </span>
        </div>
      </div>
      <div>
        <!-- button toggle sleep details -->
        <a
          class="btn btn-link btn-lg link-body-emphasis"
          data-bs-toggle="collapse"
          :href="`#collapseSleepDetails${userHealthSleep.id}`"
          role="button"
          aria-expanded="false"
          :aria-controls="`collapseSleepDetails${userHealthSleep.id}`"
        >
          <font-awesome-icon :icon="['fas', 'caret-down']" v-if="!sleepDetails" />
          <font-awesome-icon :icon="['fas', 'caret-up']" v-else />
        </a>
        <!-- source logo -->
        <span
          class="align-middle me-3 d-none d-sm-inline"
          v-if="userHealthSleep.source === 'garmin'"
        >
          <img :src="INTEGRATION_LOGOS.garminConnectApp" alt="Garmin Connect logo" height="22" />
        </span>

        <!-- edit weight button -->
        <a
          class="btn btn-link btn-lg link-body-emphasis"
          href="#"
          role="button"
          data-bs-toggle="modal"
          :data-bs-target="`#editSleepId${userHealthSleep.id}`"
          ><font-awesome-icon :icon="['fas', 'fa-pen-to-square']"
        /></a>

        <HealthSleepAddEditModalComponent
          :action="'edit'"
          :userHealthSleep="userHealthSleep"
          @editedSleep="updateSleepListEdited"
        />

        <!-- delete weight button -->
        <a
          class="btn btn-link btn-lg link-body-emphasis"
          href="#"
          role="button"
          data-bs-toggle="modal"
          :data-bs-target="`#deleteSleepModal${userHealthSleep.id}`"
          ><font-awesome-icon :icon="['fas', 'fa-trash-can']"
        /></a>

        <ModalComponent
          :modalId="`deleteSleepModal${userHealthSleep.id}`"
          :title="t('healthSleepListComponent.modalDeleteSleepTitle')"
          :body="`${t('healthSleepListComponent.modalDeleteSleepBody')}<b>${userHealthSleep.date}</b>?`"
          :actionButtonType="`danger`"
          :actionButtonText="t('healthSleepListComponent.modalDeleteSleepTitle')"
          @submitAction="submitDeleteSleep"
        />
      </div>
    </div>
    <div class="collapse" :id="`collapseSleepDetails${userHealthSleep.id}`">
      <HealthSleepListTabsComponent :userHealthSleep="userHealthSleep" />

      <h6 class="fw-semibold mb-2">
        {{ $t('healthSleepListComponent.sleepStagesTitle') }}
      </h6>
      <HealthSleepTimelineChartComponent
        :sleepStages="userHealthSleep.sleep_stages"
        v-if="userHealthSleep.sleep_stages"
      />
    </div>
  </li>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import HealthSleepAddEditModalComponent from './HealthSleepAddEditModalComponent.vue'
import HealthSleepListTabsComponent from './HealthSleepListTabsComponent.vue'
import HealthSleepTimelineChartComponent from './HealthSleepTimelineChartComponent.vue'
import ModalComponent from '@/components/Modals/ModalComponent.vue'
// Import Notivue push
import { push } from 'notivue'
// Importing the services
import { health_sleep } from '@/services/health_sleepService'
// Import constants
import { INTEGRATION_LOGOS } from '@/constants/integrationLogoConstants'
import { formatDuration, formatDateShort } from '@/utils/dateTimeUtils'

const props = defineProps({
  userHealthSleep: {
    type: Object,
    required: true
  }
})

const emit = defineEmits(['editedSleep', 'deletedSleep'])

const { t } = useI18n()
const sleepDetails = ref(false)

async function updateSleepListEdited(editedSleep) {
  try {
    await health_sleep.editHealthSleep(editedSleep)

    emit('editedSleep', editedSleep)

    push.success(t('healthSleepListComponent.successEditSleep'))
  } catch (error) {
    push.error(`${t('healthSleepListComponent.errorEditSleep')} - ${error.toString()}`)
  }
}

async function submitDeleteSleep() {
  try {
    await health_sleep.deleteHealthSleep(props.userHealthSleep.id)

    emit('deletedSleep', props.userHealthSleep.id)

    push.success(t('healthSleepListComponent.successDeleteSleep'))
  } catch (error) {
    push.error(`${t('healthSleepListComponent.errorDeleteSleep')} - ${error.toString()}`)
  }
}

onMounted(async () => {
  // Attach Bootstrap collapse event listeners to sync icon state
  const collapseElement = document.getElementById(`collapseSleepDetails${props.userHealthSleep.id}`)
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
