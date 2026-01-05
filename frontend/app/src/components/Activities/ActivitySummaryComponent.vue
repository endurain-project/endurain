<template>
  <div v-if="isLoading">
    <LoadingComponent />
  </div>
  <div v-else>
    <div class="d-flex justify-content-between">
      <!-- user name and photo zone -->
      <div class="d-flex align-items-center">
        <UserAvatarComponent :user="userActivity" :width="55" :height="55" />
        <div class="ms-3 me-3">
          <div class="fw-bold">
            <span v-if="userActivity">
              <router-link
                :to="{ name: 'user', params: { id: userActivity.id } }"
                class="link-body-emphasis link-underline-opacity-0 link-underline-opacity-100-hover"
              >
                {{ userActivity.name }}
              </router-link>
            </span>
            <span v-else>
              {{ $t('activitySummaryComponent.userNameHidden') }}
            </span>
          </div>
          <h6>
            <!-- Display the visibility of the activity -->
            <span v-if="activity.visibility == 0">
              <font-awesome-icon :icon="['fas', 'globe']" />
              {{ $t('activitySummaryComponent.visibilityPublic') }}
            </span>
            <span v-if="activity.visibility == 1">
              <font-awesome-icon :icon="['fas', 'users']" v-if="activity.visibility == 1" />
              {{ $t('activitySummaryComponent.visibilityFollowers') }}
            </span>
            <span v-if="activity.visibility == 2">
              <font-awesome-icon :icon="['fas', 'lock']" v-if="activity.visibility == 2" />
              {{ $t('activitySummaryComponent.visibilityPrivate') }}
            </span>
            <span> - </span>

            <!-- Display the activity type -->
            <span>
              <font-awesome-icon class="me-1" :icon="getIcon(activity.activity_type)" />
              <span v-if="activity.activity_type === 3 || activity.activity_type === 7">{{
                $t('activitySummaryComponent.labelVirtual')
              }}</span>
            </span>

            <!-- Display the date and time -->
            <span v-if="activity.start_time_tz_applied">
              {{ formatDateMed(activity.start_time_tz_applied) }} @
              {{ formatTime(activity.start_time_tz_applied) }}
            </span>
            <!-- Conditionally display city and country -->
            <span v-if="activity.city || activity.town || activity.country">
              -
              <span>{{ formatLocation(t, activity) }}</span>
            </span>
          </h6>
        </div>
      </div>
      <div class="dropdown d-flex" v-if="activity.user_id == authStore.user.id">
        <a
          class="btn btn-link btn-lg link-body-emphasis"
          :href="`https://www.strava.com/activities/${activity.strava_activity_id}`"
          role="button"
          v-if="activity.strava_activity_id"
        >
          <font-awesome-icon :icon="['fab', 'fa-strava']" />
        </a>
        <a
          class="btn btn-link btn-lg link-body-emphasis"
          :href="`https://connect.garmin.com/modern/activity/${activity.garminconnect_activity_id}`"
          role="button"
          v-if="activity.garminconnect_activity_id"
        >
          <img :src="INTEGRATION_LOGOS.garminConnectApp" alt="Garmin Connect logo" height="22" />
        </a>
        <div>
          <button
            class="btn btn-link btn-lg link-body-emphasis"
            type="button"
            data-bs-toggle="dropdown"
            aria-expanded="false"
          >
            <font-awesome-icon :icon="['fas', 'fa-ellipsis-vertical']" />
          </button>
          <ul class="dropdown-menu">
            <li v-if="source === 'activity'">
              <a
                class="dropdown-item"
                href="#"
                data-bs-toggle="modal"
                data-bs-target="#addActivityMediaModal"
              >
                {{ $t('activitySummaryComponent.buttonAddActivityMedia') }}
              </a>
            </li>
            <li v-if="source === 'activity'">
              <hr class="dropdown-divider" />
            </li>
            <li v-if="source === 'activity'">
              <a
                class="dropdown-item"
                href="#"
                data-bs-toggle="modal"
                data-bs-target="#editActivityModal"
              >
                {{ $t('activitySummaryComponent.buttonEditActivity') }}
              </a>
            </li>
            <li v-if="source === 'activity'">
              <hr class="dropdown-divider" />
            </li>
            <li>
              <a
                class="dropdown-item"
                href="#"
                data-bs-toggle="modal"
                :data-bs-target="`#deleteActivityModal${activity.id}`"
              >
                {{ $t('activitySummaryComponent.buttonDeleteActivity') }}
              </a>
            </li>
          </ul>
        </div>
      </div>
    </div>

    <!-- Modal add media -->
    <ModalComponentUploadFile
      modalId="addActivityMediaModal"
      :title="$t('activitySummaryComponent.modalAddMediaTitle')"
      :fileFieldLabel="$t('activitySummaryComponent.modalAddMediaBody')"
      filesAccepted=".png, .jpg, .jpeg"
      actionButtonType="success"
      :actionButtonText="$t('activitySummaryComponent.modalAddMediaTitle')"
      @fileToEmitAction="submitUploadMediaForm"
    />

    <!-- Modal edit activity -->
    <EditActivityModalComponent
      :activity="activity"
      @activityEditedFields="updateActivityFieldsOnEdit"
    />

    <!-- Modal delete activity -->
    <ModalComponent
      :modalId="`deleteActivityModal${activity.id}`"
      :title="t('activitySummaryComponent.buttonDeleteActivity')"
      :body="`${t('activitySummaryComponent.modalDeleteBody1')}<b>${activity.name}</b>?<br>${t('activitySummaryComponent.modalDeleteBody2')}`"
      :actionButtonType="`danger`"
      :actionButtonText="t('activitySummaryComponent.buttonDeleteActivity')"
      @submitAction="submitDeleteActivity"
    />

    <!-- Activity title -->
    <h5 class="mt-3" v-if="source === 'home'">
      <router-link
        :to="{ name: 'activity', params: { id: activity.id } }"
        class="link-body-emphasis link-underline-opacity-0 link-underline-opacity-100-hover"
      >
        <span v-if="activity.name === 'Workout'">{{ formatName(activity, t) }}</span>
        <span v-else>{{ activity.name }}</span>
      </router-link>
    </h5>
    <h1 class="mt-3" v-if="source === 'activity'">
      <span v-if="activity.name === 'Workout'">{{ formatName(activity, t) }}</span>
      <span v-else>{{ activity.name }}</span>
    </h1>

    <!-- Activity description -->
    <p v-if="activity.description">{{ activity.description }}</p>

    <div v-if="activity.private_notes">
      <hr />
      <h6 class="text-body-secondary">
        {{ $t('activitySummaryComponent.privateNotes') }}
      </h6>
      <p>{{ activity.private_notes }}</p>
      <hr />
    </div>

    <!-- Activity summary -->
    <div class="row mt-3 align-items-center text-start">
      <!-- distance -->
      <div
        class="col"
        v-if="
          activity.activity_type != 10 &&
          activity.activity_type != 14 &&
          activity.activity_type != 18 &&
          activity.activity_type != 19 &&
          activity.activity_type != 20 &&
          activity.activity_type != 41 &&
          activity.activity_type != 46 &&
          activityTypeNotRacquet(activity)
        "
      >
        <span class="fw-lighter">
          {{ $t('activitySummaryComponent.activityDistance') }}
        </span>
        <br />
        <span>{{ formatDistance(t, activity, units) }}</span>
      </div>
      <!-- calories -->
      <div class="col" v-else>
        <span class="fw-lighter">
          {{ $t('activitySummaryComponent.activityCalories') }}
        </span>
        <br />
        <span>{{ formatCalories(t, activity.calories) }}</span>
      </div>
      <!-- activity time-->
      <div class="col border-start border-opacity-50">
        <span class="fw-lighter">
          {{ $t('activitySummaryComponent.activityTime') }}
        </span>
        <br />
        <span>{{ formatSecondsToMinutes(activity.total_elapsed_time) }}</span>
      </div>
      <div class="col border-start border-opacity-50">
        <!-- elevation -->
        <div v-if="activityTypeIsCycling(activity)">
          <span class="fw-lighter">
            {{ $t('activitySummaryComponent.activityEleGain') }}
          </span>
          <br />
          <span>{{ formatElevation(t, activity.elevation_gain, units) }}</span>
        </div>
        <!-- pace -->
        <div
          v-else-if="
            activity.activity_type != 10 &&
            activity.activity_type != 14 &&
            activity.activity_type != 18 &&
            activity.activity_type != 19 &&
            activity.activity_type != 20 &&
            activityTypeNotWindsurf(activity) &&
            activity.activity_type != 41 &&
            activity.activity_type != 46 &&
            activityTypeNotSailing(activity) &&
            activityTypeNotRacquet(activity)
          "
        >
          <span class="fw-lighter">
            {{ $t('activitySummaryComponent.activityPace') }}
          </span>
          <br />
          {{ formatPace(t, activity, units) }}
        </div>
        <!-- avg_speed sailing activities -->
        <div v-else-if="activityTypeIsWindsurf(activity) || activityTypeIsSailing(activity)">
          <span class="fw-lighter">
            {{ $t('activitySummaryComponent.activityAvgSpeed') }}
          </span>
          <br />
          <span>{{ formatAverageSpeed(t, activity, units) }}</span>
        </div>
        <!-- avg_hr -->
        <div v-else>
          <span class="fw-lighter">
            {{ $t('activitySummaryComponent.activityAvgHR') }}
          </span>
          <br />
          <span>{{ formatHr(t, activity.average_hr) }}</span>
        </div>
      </div>
    </div>
    <div
      class="row d-flex mt-3"
      v-if="
        source === 'activity' &&
        activity.activity_type != 10 &&
        activity.activity_type != 14 &&
        activity.activity_type != 18 &&
        activity.activity_type != 19 &&
        activity.activity_type != 20 &&
        activity.activity_type != 41 &&
        activity.activity_type != 46 &&
        activityTypeNotRacquet(activity)
      "
    >
      <!-- avg_power running and cycling activities-->
      <div class="col" v-if="activityTypeIsCycling(activity) || activityTypeIsRunning(activity)">
        <span class="fw-lighter">
          {{ $t('activitySummaryComponent.activityAvgPower') }}
        </span>
        <br />
        <span>{{ formatPower(t, activity.average_power) }}</span>
      </div>
      <!-- avg_hr not running and cycling activities-->
      <div class="col" v-if="activityTypeNotCycling(activity) && activityTypeNotRunning(activity)">
        <span class="fw-lighter">
          {{ $t('activitySummaryComponent.activityAvgHR') }}
        </span>
        <br />
        <span>{{ formatHr(t, activity.average_hr) }}</span>
      </div>
      <!-- max_hr not running and cycling activities-->
      <div
        class="col border-start border-opacity-50"
        v-if="activityTypeNotCycling(activity) && activityTypeNotRunning(activity)"
      >
        <span class="fw-lighter">
          {{ $t('activitySummaryComponent.activityMaxHR') }}
        </span>
        <br />
        <span>{{ formatHr(t, activity.max_hr) }}</span>
      </div>
      <!-- ele gain running activities -->
      <div class="col border-start border-opacity-50" v-if="activityTypeIsRunning(activity)">
        <span class="fw-lighter">{{ $t('activitySummaryComponent.activityEleGain') }}</span>
        <br />
        <span>{{ formatElevation(t, activity.elevation_gain, units) }}</span>
      </div>
      <!-- avg_speed cycling activities -->
      <div class="col border-start border-opacity-50" v-if="activityTypeIsCycling(activity)">
        <span class="fw-lighter">
          {{ $t('activitySummaryComponent.activityAvgSpeed') }}
        </span>
        <br />
        <span>{{ formatAverageSpeed(t, activity, units) }}</span>
      </div>
      <!-- calories -->
      <div class="col border-start border-opacity-50">
        <span class="fw-lighter">
          {{ $t('activitySummaryComponent.activityCalories') }}
        </span>
        <br />
        <span>{{ formatCalories(t, activity.calories) }}</span>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRouter } from 'vue-router'
// Importing the stores
import { useAuthStore } from '@/stores/authStore'
import { useServerSettingsStore } from '@/stores/serverSettingsStore'
// Import Notivue push
import { push } from 'notivue'
// Importing the components
import LoadingComponent from '@/components/GeneralComponents/LoadingComponent.vue'
import UserAvatarComponent from '@/components/Users/UserAvatarComponent.vue'
import ModalComponentUploadFile from '@/components/Modals/ModalComponentUploadFile.vue'
import EditActivityModalComponent from '@/components/Activities/Modals/EditActivityModalComponent.vue'
import ModalComponent from '@/components/Modals/ModalComponent.vue'
// Importing constants
import { INTEGRATION_LOGOS } from '@/constants/integrationLogoConstants'
// Importing the services
import { users } from '@/services/usersService'
import { activities } from '@/services/activitiesService'
import { activityMedia } from '@/services/activityMediaService'
// Importing the utils
import {
  formatDistance,
  formatElevation,
  formatPace,
  formatHr,
  formatCalories,
  getIcon,
  formatLocation,
  formatAverageSpeed,
  formatPower,
  activityTypeIsCycling,
  activityTypeNotCycling,
  activityTypeIsRunning,
  activityTypeNotRunning,
  activityTypeNotRacquet,
  activityTypeNotWindsurf,
  activityTypeIsWindsurf,
  activityTypeNotSailing,
  activityTypeIsSailing,
  formatName
} from '@/utils/activityUtils'
import { formatDateMed, formatTime, formatSecondsToMinutes } from '@/utils/dateTimeUtils'

// Props
const props = defineProps({
  activity: {
    type: Object,
    required: true
  },
  source: {
    type: String,
    required: true
  },
  units: {
    type: Number,
    default: 1
  }
})

// Emits
const emit = defineEmits(['activityEditedFields', 'activityDeleted', 'activityNewActivityMedia'])

// Composables
const router = useRouter()
const authStore = useAuthStore()
const serverSettingsStore = useServerSettingsStore()
const { t } = useI18n()

// Reactive data
const isLoading = ref(true)
const userActivity = ref(null)

// Lifecycle
onMounted(async () => {
  try {
    if (authStore.isAuthenticated) {
      userActivity.value = await users.getUserById(props.activity.user_id)
    } else {
      if (serverSettingsStore.serverSettings.public_shareable_links_user_info) {
        userActivity.value = await users.getPublicUserById(props.activity.user_id)
      }
    }
  } catch (error) {
    push.error(`${t('activitySummaryComponent.errorFetchingUserById')} - ${error}`)
  } finally {
    isLoading.value = false
  }
})

// Methods
async function submitDeleteActivity() {
  try {
    await activities.deleteActivity(props.activity.id)
    if (props.source === 'activity') {
      return router.push({
        path: '/',
        query: { activityDeleted: 'true', activityId: props.activity.id }
      })
    }
    emit('activityDeleted', props.activity.id)
  } catch (error) {
    push.error(`${t('activitySummaryComponent.errorDeletingActivity')} - ${error}`)
  }
}

function updateActivityFieldsOnEdit(data) {
  // Emit the activityEditedFields event to the parent component
  emit('activityEditedFields', data)
}

const submitUploadMediaForm = async (file) => {
  // Set the loading message
  const notification = push.promise(t('activitySummaryComponent.processingMediaUpload'))

  // If there is a file, create the form data and upload the file
  if (file) {
    try {
      // Upload the file
      const newActivityMedia = await activityMedia.uploadActivityMediaFile(props.activity.id, file)

      emit('activityNewActivityMedia', newActivityMedia)

      // Set the success message
      notification.resolve(t('activitySummaryComponent.successMediaUpload'))
    } catch (error) {
      // Set the error message
      notification.reject(`${t('activitySummaryComponent.errorMediaUpload')} - ${error}`)
    }
  }
}
</script>
