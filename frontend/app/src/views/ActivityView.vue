<template>
  <div
    class="bg-body-tertiary rounded p-3 shadow-sm"
    :class="{ 'border border-warning border-2': activity?.is_hidden }"
  >
    <LoadingComponent v-if="isLoading" />

    <div v-else>
      <ActivitySummaryComponent
        v-if="activity"
        :activity="activity"
        :source="'activity'"
        @activityEditedFields="updateActivityFieldsOnEdit"
        @activityNewActivityMedia="addMediaToActivity"
        :units="units"
      />
      <AlertComponent
        v-if="activity && activity.user_id === authStore.user.id && activity.is_hidden"
        :message="isHiddenMessage"
        :dismissible="true"
        :type="'warning'"
        class="mt-2"
      />
      <AlertComponent
        v-if="
          activity &&
          activity.user_id === authStore.user.id &&
          (activity.hide_start_time ||
            activity.hide_location ||
            activity.hide_map ||
            activity.hide_hr ||
            activity.hide_power ||
            activity.hide_cadence ||
            activity.hide_elevation ||
            activity.hide_speed ||
            activity.hide_pace ||
            activity.hide_laps ||
            activity.hide_workout_sets_steps ||
            activity.hide_gear)
        "
        :message="alertPrivacyMessage"
        :dismissible="true"
        class="mt-2"
      />
    </div>

    <!-- map zone -->
    <div class="mt-3 mb-3" v-if="isLoading">
      <LoadingComponent />
    </div>
    <div
      class="mt-3 mb-3"
      v-else-if="
        activity &&
        ((authStore.isAuthenticated && authStore.user.id === activity.user_id) ||
          (authStore.isAuthenticated &&
            authStore.user.id !== activity.user_id &&
            activity.hide_map === false) ||
          (!authStore.isAuthenticated && activity.hide_map === false))
      "
    >
      <ActivityMapComponent
        :activity="activity"
        :activityActivityMedia="activityActivityMedia"
        :source="'activity'"
        @activityMediaDeleted="removeMediaFromActivity"
      />
    </div>

    <!-- gear zone -->
    <hr
      class="mb-2 mt-2"
      v-if="
        activity &&
        ((authStore.isAuthenticated && authStore.user.id === activity.user_id) ||
          (authStore.isAuthenticated &&
            authStore.user.id !== activity.user_id &&
            activity.hide_gear === false))
      "
    />
    <div class="mt-3 mb-3" v-if="isLoading && authStore.isAuthenticated">
      <LoadingComponent />
    </div>
    <div
      class="d-flex justify-content-between align-items-center"
      v-else-if="
        activity &&
        ((authStore.isAuthenticated && authStore.user.id === activity.user_id) ||
          (authStore.isAuthenticated &&
            authStore.user.id !== activity.user_id &&
            activity.hide_gear === false))
      "
    >
      <p class="pt-2">
        <span class="fw-lighter">
          {{ $t('activityView.labelGear') }}
        </span>
        <br />
        <span v-if="activityTypeIsRunning(activity)">
          <font-awesome-icon :icon="['fas', 'person-running']" />
        </span>
        <span v-else-if="activityTypeIsCycling(activity)">
          <font-awesome-icon :icon="['fas', 'fa-person-biking']" />
        </span>
        <span v-else-if="activityTypeIsSwimming(activity)">
          <font-awesome-icon :icon="['fas', 'fa-person-swimming']" />
        </span>
        <span v-else-if="activityTypeIsRacquet(activity)">
          <font-awesome-icon :icon="['fas', 'fa-table-tennis-paddle-ball']" />
        </span>
        <span v-else-if="activityTypeIsWindsurf(activity)">
          <font-awesome-icon :icon="['fas', 'wind']" />
        </span>
        <span class="ms-2" v-if="activity.gear_id && gear">{{ gear.nickname }}</span>
        <span class="ms-2" v-else>{{ $t('activityView.labelGearNotSet') }}</span>
      </p>
      <div class="justify-content-end">
        <!-- add gear button -->
        <a
          class="btn btn-link btn-lg link-body-emphasis"
          href="#"
          role="button"
          data-bs-toggle="modal"
          data-bs-target="#addGearToActivityModal"
          v-if="!activity.gear_id && activity.user_id === authStore.user.id"
        >
          <font-awesome-icon :icon="['fas', 'fa-plus']" />
        </a>

        <!-- add gear to activity modal -->
        <AddGearToActivityModalComponent
          :activity="activity"
          :gearsByType="gearsByType"
          :gear="gearId"
          @gearId="updateGearIdOnAddGearToActivity"
        />

        <!-- edit gear button -->
        <a
          class="btn btn-link btn-lg link-body-emphasis"
          href="#"
          role="button"
          data-bs-toggle="modal"
          data-bs-target="#addGearToActivityModal"
          v-if="activity.gear_id && activity.user_id === authStore.user.id"
        >
          <font-awesome-icon :icon="['far', 'fa-pen-to-square']" />
        </a>

        <!-- Delete zone -->
        <a
          class="btn btn-link btn-lg link-body-emphasis"
          href="#"
          role="button"
          data-bs-toggle="modal"
          data-bs-target="#deleteGearActivityModal"
          v-if="activity.gear_id && activity.user_id === authStore.user.id"
        >
          <font-awesome-icon :icon="['fas', 'fa-trash']" />
        </a>

        <!-- Modal delete gear -->
        <ModalComponent
          modalId="deleteGearActivityModal"
          :title="t('activityView.modalLabelDeleteGear')"
          :body="`${t('activityView.modalLabelDeleteGearBody')}`"
          actionButtonType="danger"
          :actionButtonText="t('activityView.modalLabelDeleteGearButton')"
          @submitAction="submitDeleteGearFromActivity"
        />
      </div>
    </div>

    <!-- graphs -->
    <hr
      class="mb-2 mt-2"
      v-if="
        activity &&
        ((activityActivityLaps && activityActivityLaps.length > 0) ||
          (activityActivityWorkoutSteps && activityActivityWorkoutSteps.length > 0) ||
          (activityActivitySets && activityActivitySets.length > 0) ||
          (activityActivityStreams && activityActivityStreams.length > 0))
      "
    />

    <!-- graphs and laps medium and above screens -->
    <div class="d-none d-lg-block" v-if="isLoading">
      <LoadingComponent />
    </div>
    <div
      class="d-none d-lg-block"
      v-else-if="
        activity &&
        ((activityActivityLaps && activityActivityLaps.length > 0) ||
          (activityActivityWorkoutSteps && activityActivityWorkoutSteps.length > 0) ||
          (activityActivitySets && activityActivitySets.length > 0) ||
          (activityActivityStreams && activityActivityStreams.length > 0))
      "
    >
      <ActivityMandAbovePillsComponent
        :activity="activity"
        :activityActivityLaps="activityActivityLaps"
        :activityActivityWorkoutSteps="activityActivityWorkoutSteps"
        :activityActivityStreams="activityActivityStreams"
        :units="units"
        :activityActivityExerciseTitles="activityActivityExerciseTitles"
        :activityActivitySets="activityActivitySets"
      />
    </div>

    <!-- graphs and laps screens bellow medium -->
    <div class="d-lg-none d-block" v-if="isLoading">
      <LoadingComponent />
    </div>
    <div
      class="d-lg-none d-block"
      v-else-if="
        activity &&
        ((activityActivityLaps && activityActivityLaps.length > 0) ||
          (activityActivityWorkoutSteps && activityActivityWorkoutSteps.length > 0) ||
          (activityActivitySets && activityActivitySets.length > 0) ||
          (activityActivityStreams && activityActivityStreams.length > 0))
      "
    >
      <ActivityBellowMPillsComponent
        :activity="activity"
        :activityActivityLaps="activityActivityLaps"
        :activityActivityWorkoutSteps="activityActivityWorkoutSteps"
        :activityActivityStreams="activityActivityStreams"
        :units="units"
        :activityActivityExerciseTitles="activityActivityExerciseTitles"
        :activityActivitySets="activityActivitySets"
      />
    </div>

    <!-- back button -->
    <BackButtonComponent />
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRoute, useRouter } from 'vue-router'
// Importing the stores
import { useAuthStore } from '@/stores/authStore'
import { useServerSettingsStore } from '@/stores/serverSettingsStore'
// Import Notivue push
import { push } from 'notivue'
// Importing the components
import ActivitySummaryComponent from '@/components/Activities/ActivitySummaryComponent.vue'
import ActivityMapComponent from '@/components/Activities/ActivityMapComponent.vue'
import ActivityMandAbovePillsComponent from '@/components/Activities/ActivityMandAbovePillsComponent.vue'
import ActivityBellowMPillsComponent from '@/components/Activities/ActivityBellowMPillsComponent.vue'
import LoadingComponent from '@/components/GeneralComponents/LoadingComponent.vue'
import BackButtonComponent from '@/components/GeneralComponents/BackButtonComponent.vue'
import ModalComponent from '@/components/Modals/ModalComponent.vue'
import AddGearToActivityModalComponent from '@/components/Activities/Modals/AddGearToActivityModalComponent.vue'
import AlertComponent from '@/components/GeneralComponents/AlertComponent.vue'
// Importing the services
import { gears } from '@/services/gearsService'
import { activities } from '@/services/activitiesService'
import { activityStreams } from '@/services/activityStreams'
import { activityLaps } from '@/services/activityLapsService'
import { activityWorkoutSteps } from '@/services/activityWorkoutStepsService'
import { activityExerciseTitles } from '@/services/activityExerciseTitlesService'
import { activitySets } from '@/services/activitySetsService'
import { activityMedia } from '@/services/activityMediaService'
// Importing the utils
import {
  activityTypeIsCycling,
  activityTypeIsRunning,
  activityTypeIsWalking,
  activityTypeIsSwimming,
  activityTypeIsRacquet,
  activityTypeIsWindsurf,
  activityTypeIsSnowSkiing,
  activityTypeIsSnowboarding,
  activityTypeIsSurf,
  activityTypeIsStandUpPaddling
} from '@/utils/activityUtils'

const { t } = useI18n()
const authStore = useAuthStore()
const serverSettingsStore = useServerSettingsStore()
const route = useRoute()
const router = useRouter()
const isLoading = ref(true)
const activity = ref(null)
const gear = ref(null)
const gearsByType = ref([])
const gearId = ref(null)
const activityActivityStreams = ref([])
const activityActivityLaps = ref([])
const activityActivityWorkoutSteps = ref([])
const activityActivityMedia = ref([])
const units = ref(1)
const activityActivityExerciseTitles = ref([])
const activityActivitySets = ref([])
const alertPrivacyMessage = ref(null)
const isHiddenMessage = ref(null)

async function submitDeleteGearFromActivity() {
  try {
    // Delete the gear from the activity
    const auxActivity = activity.value
    auxActivity.gear_id = null
    await activities.editActivity(auxActivity)

    // Show the success message
    push.success(t('activityView.successMessageGearDeleted'))

    // Update the activity gear
    activity.value.gear_id = null
  } catch (error) {
    push.error(`${t('activityView.errorMessageDeleteGear')} - ${error}`)
  }
}

async function updateGearIdOnAddGearToActivity(gearId) {
  // Update the activity gear
  gear.value = await gears.getGearById(gearId)
  activity.value.gear_id = gearId

  // Show the success message
  push.success(t('activityView.successMessageGearAdded'))
}

async function updateActivityFieldsOnEdit(data) {
  let activityTypeChanged = false
  if (activity.value.activity_type !== data.activity_type) {
    activityTypeChanged = true
  }

  // Update the activity fields
  activity.value.name = data.name
  activity.value.description = data.description
  activity.value.private_notes = data.private_notes
  activity.value.activity_type = Number(data.activity_type)
  activity.value.visibility = data.visibility
  activity.value.is_hidden = data.is_hidden
  activity.value.hide_start_time = data.hide_start_time
  activity.value.location = data.location
  activity.value.hide_map = data.hide_map
  activity.value.hide_hr = data.hide_hr
  activity.value.hide_power = data.hide_power
  activity.value.hide_cadence = data.hide_cadence
  activity.value.hide_elevation = data.hide_elevation
  activity.value.hide_speed = data.hide_speed
  activity.value.hide_pace = data.hide_pace
  activity.value.hide_laps = data.hide_laps
  activity.value.hide_workout_sets_steps = data.hide_workout_sets_steps
  activity.value.hide_gear = data.hide_gear

  if (activityTypeChanged) {
    await getGearsByActivityType()
  }
}

function addMediaToActivity(media) {
  // Add the media to the activity
  if (!Array.isArray(activityActivityMedia.value)) {
    activityActivityMedia.value = []
  }
  activityActivityMedia.value.unshift(media)
}

function removeMediaFromActivity(mediaId) {
  // Remove the media from the activity
  if (Array.isArray(activityActivityMedia.value)) {
    activityActivityMedia.value = activityActivityMedia.value.filter(
      (media) => media.id !== mediaId
    )
  }
}

async function getGearsByActivityType() {
  if (activityTypeIsCycling(activity.value)) {
    gearsByType.value = await gears.getGearFromType(1)
  } else if (activityTypeIsRunning(activity.value) || activityTypeIsWalking(activity.value)) {
    gearsByType.value = await gears.getGearFromType(2)
  } else if (activityTypeIsSwimming(activity.value)) {
    gearsByType.value = await gears.getGearFromType(3)
  } else if (activityTypeIsRacquet(activity.value)) {
    gearsByType.value = await gears.getGearFromType(4)
  } else if (activityTypeIsSnowSkiing(activity.value)) {
    gearsByType.value = await gears.getGearFromType(5)
  } else if (activityTypeIsSnowboarding(activity.value)) {
    gearsByType.value = await gears.getGearFromType(6)
  } else if (activityTypeIsWindsurf(activity.value)) {
    gearsByType.value = await gears.getGearFromType(7)
  } else if (activityTypeIsStandUpPaddling(activity.value) || activityTypeIsSurf(activity.value)) {
    gearsByType.value = await gears.getGearFromType(8)
  } else {
    gearsByType.value = []
  }
}

onMounted(async () => {
  try {
    // Get the activity by id
    if (authStore.isAuthenticated) {
      activity.value = await activities.getActivityById(route.params.id)
    } else {
      if (serverSettingsStore.serverSettings.public_shareable_links) {
        activity.value = await activities.getPublicActivityById(route.params.id)
        if (!activity.value) {
          return router.push({
            path: '/login',
            query: { errorPublicActivityNotFound: 'true' }
          })
        }
      } else {
        return router.push({
          path: '/login',
          query: { errorpublic_shareable_links: 'true' }
        })
      }
    }

    // Check if the activity exists
    if (!activity.value) {
      return router.push({
        path: '/',
        query: { activityFound: 'false', id: route.params.id }
      })
    }

    if (authStore.isAuthenticated) {
      // Set the units
      units.value = authStore.user.units

      // Get the activity streams by activity id
      activityActivityStreams.value = await activityStreams.getActivitySteamsByActivityId(
        route.params.id
      )

      // Get the activity laps by activity id
      activityActivityLaps.value = await activityLaps.getActivityLapsByActivityId(route.params.id)

      // Get the activity workout steps by activity id
      activityActivityWorkoutSteps.value =
        await activityWorkoutSteps.getActivityWorkoutStepsByActivityId(route.params.id)

      // Get the activity exercise titles
      activityActivityExerciseTitles.value =
        await activityExerciseTitles.getActivityExerciseTitlesAll()

      // Get the activity sets by activity id
      activityActivitySets.value = await activitySets.getActivitySetsByActivityId(route.params.id)

      // Get the activity media by activity id
      activityActivityMedia.value = await activityMedia.getUserActivityMediaByActivityId(
        route.params.id
      )
    } else {
      // Set the units
      units.value = serverSettingsStore.serverSettings.units

      // Get the activity streams by activity id
      activityActivityStreams.value = await activityStreams.getPublicActivityStreamsByActivityId(
        route.params.id
      )

      // Get the activity laps by activity id
      activityActivityLaps.value = await activityLaps.getPublicActivityLapsByActivityId(
        route.params.id
      )

      // Get the activity workout steps by activity id
      activityActivityWorkoutSteps.value =
        await activityWorkoutSteps.getPublicActivityWorkoutStepsByActivityId(route.params.id)

      // Get the activity exercise titles
      activityActivityExerciseTitles.value =
        await activityExerciseTitles.getPublicActivityExerciseTitlesAll()

      // Get the activity sets by activity id
      activityActivitySets.value = await activitySets.getPublicActivitySetsByActivityId(
        route.params.id
      )
    }

    if (authStore.isAuthenticated) {
      if (activity.value.gear_id) {
        gear.value = await gears.getGearById(activity.value.gear_id)
        gearId.value = activity.value.gear_id
      }

      await getGearsByActivityType()
    }
  } catch (error) {
    if (error.toString().includes('422')) {
      router.push({
        path: '/',
        query: { activityFound: 'false', id: route.params.id }
      })
    }
    // If there is an error, set the error message and show the error alert.
    push.error(`${t('activityView.errorMessageActivityNotFound')} - ${error}`)
  }

  isLoading.value = false
  if (authStore.user.id === activity.value.user_id) {
    alertPrivacyMessage.value = t('activityView.alertPrivacyMessage')
    isHiddenMessage.value = t('activityView.isHiddenMessage')
  }
})
</script>
