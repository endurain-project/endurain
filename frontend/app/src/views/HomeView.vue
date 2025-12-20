<template>
  <div class="row">
    <!-- sidebar zone -->
    <div class="col-lg-3 col-md-12">
      <div class="d-none d-lg-block d-flex mb-3 rounded p-3 bg-body-tertiary shadow-sm">
        <!-- user name and photo zone -->
        <div v-if="isLoading">
          <LoadingComponent />
        </div>
        <div v-else>
          <div class="justify-content-center d-flex" v-if="authStore.user">
            <UserAvatarComponent :user="authStore.user" :width="120" :height="120" />
          </div>
          <div class="text-center mt-3 fw-bold" v-if="authStore.user.id">
            <router-link
              :to="{ name: 'user', params: { id: authStore.user.id } }"
              class="link-body-emphasis link-underline-opacity-0 link-underline-opacity-100-hover fs-4"
            >
              {{ authStore.user.name }}
            </router-link>
          </div>
        </div>
      </div>
      <div class="d-none d-lg-block d-flex mb-3 rounded p-3 bg-body-tertiary shadow-sm">
        <!-- user stats zone -->
        <div v-if="isLoading">
          <LoadingComponent />
        </div>
        <UserDistanceStatsComponent
          v-else
          :thisWeekDistances="thisWeekDistances"
          :thisMonthDistances="thisMonthDistances"
        />
      </div>

      <!-- add activity and refresh buttons -->
      <div class="row mb-3">
        <div class="col">
          <a
            class="w-100 btn btn-primary shadow-sm"
            href="#"
            role="button"
            data-bs-toggle="modal"
            data-bs-target="#addActivityModal"
          >
            {{ $t('homeView.buttonAddActivity') }}
          </a>
        </div>
        <div
          class="col-auto"
          v-if="authStore.user.is_strava_linked == 1 || authStore.user.is_garminconnect_linked == 1"
        >
          <a
            class="w-100 btn btn-primary shadow-sm"
            href="#"
            role="button"
            @click="refreshActivities"
          >
            <font-awesome-icon :icon="['fas', 'arrows-rotate']" />
          </a>
        </div>
      </div>

      <!-- Modal add actvity -->
      <ModalComponentUploadFile
        modalId="addActivityModal"
        :title="$t('homeView.buttonAddActivity')"
        :fileFieldLabel="$t('homeView.fieldLabelUploadFileType')"
        filesAccepted=".gz,.gpx,.fit,.tcx"
        actionButtonType="success"
        :actionButtonText="$t('homeView.buttonAddActivity')"
        @fileToEmitAction="submitUploadFileForm"
      />
    </div>
    <!-- activities zone -->
    <div class="col">
      <!-- radio button -->
      <div
        class="btn-group mb-3 d-flex"
        role="group"
        aria-label="Activities radio toggle button group"
      >
        <!-- user activities -->
        <input
          type="radio"
          class="btn-check"
          name="btnradio"
          id="btnRadioUserActivities"
          autocomplete="off"
          value="userActivities"
          v-model="selectedActivityView"
        />
        <label class="btn btn-outline-primary w-100" for="btnRadioUserActivities">{{
          $t('homeView.radioUserActivities')
        }}</label>
        <!-- user followers activities -->
        <input
          type="radio"
          class="btn-check"
          name="btnradio"
          id="btnRadioFollowersActivities"
          autocomplete="off"
          value="followersActivities"
          v-model="selectedActivityView"
        />
        <label class="btn btn-outline-primary w-100" for="btnRadioFollowersActivities">{{
          $t('homeView.radioFollowerActivities')
        }}</label>
      </div>

      <!-- user activities -->
      <div id="userActivitiesDiv" v-show="selectedActivityView === 'userActivities'">
        <div v-if="isLoading">
          <LoadingComponent />
        </div>
        <div v-else>
          <!-- Checking if userActivities is loaded and has length -->
          <div v-if="userActivities && userActivities.length">
            <!-- Iterating over userActivities to display them -->
            <div
              class="card mb-3 bg-body-tertiary shadow-sm"
              :class="{
                'border-0': !activity.is_hidden,
                'border border-warning border-2': activity.is_hidden
              }"
              v-for="activity in userActivities"
              :key="activity.id"
            >
              <div class="card-body">
                <span class="badge rounded-pill text-bg-warning mb-3" v-if="activity.is_hidden">{{
                  $t('homeView.pillIsHidden')
                }}</span>
                <ActivitySummaryComponent
                  :activity="activity"
                  :source="'home'"
                  @activityDeleted="updateActivitiesOnDelete"
                  :units="authStore.user.units"
                />
              </div>
              <ActivityMapComponent
                class="mx-3 mb-3"
                :key="selectedActivityView + '-' + activity.id"
                :activity="activity"
                :activityActivityMedia="activityMediaMap[activity.id]"
                :source="'home'"
              />
            </div>
          </div>
          <!-- Displaying a message or component when there are no activities -->
          <NoItemsFoundComponent v-else />
        </div>
      </div>

      <!-- user followers activities -->
      <div id="followersActivitiesDiv" v-show="selectedActivityView === 'followersActivities'">
        <div v-if="isLoading">
          <LoadingComponent />
        </div>
        <div v-else>
          <div v-if="followedUserActivities && followedUserActivities.length">
            <div
              class="card mb-3 bg-body-tertiary shadow-sm border-0"
              v-for="activity in followedUserActivities"
              :key="activity.id"
            >
              <div class="card-body">
                <ActivitySummaryComponent
                  :activity="activity"
                  :source="'home'"
                  :units="authStore.user.units"
                />
              </div>
              <ActivityMapComponent
                class="mx-3 mb-3"
                :key="selectedActivityView + '-' + activity.id"
                :activity="activity"
                :activityActivityMedia="activityMediaMap[activity.id]"
                :source="'home'"
              />
            </div>
          </div>
          <NoItemsFoundComponent v-else />
        </div>
      </div>
    </div>

    <div class="col-lg-3">
      <div>
        <div class="d-none d-lg-block d-flex mb-3 rounded p-3 bg-body-tertiary shadow-sm">
          <div v-if="isLoading">
            <LoadingComponent />
          </div>
          <UserGoalsStatsComponent :goals="userGoals" v-else />
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted, onUnmounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRoute } from 'vue-router'
// Import the stores
import { useAuthStore } from '@/stores/authStore'
import { useServerSettingsStore } from '@/stores/serverSettingsStore'
// Import the services
import { activities } from '@/services/activitiesService'
import { userGoals as userGoalsService } from '@/services/userGoalsService'
import { activityMedia } from '@/services/activityMediaService'
// Import Notivue push
import { push } from 'notivue'
// Importing the components
import UserDistanceStatsComponent from '@/components/Users/UserDistanceStatsComponent.vue'
import UserGoalsStatsComponent from '@/components/Users/UserGoalsStatsComponent.vue'
import NoItemsFoundComponent from '@/components/GeneralComponents/NoItemsFoundComponents.vue'
import ActivitySummaryComponent from '@/components/Activities/ActivitySummaryComponent.vue'
import ActivityMapComponent from '@/components/Activities/ActivityMapComponent.vue'
import LoadingComponent from '@/components/GeneralComponents/LoadingComponent.vue'
import UserAvatarComponent from '@/components/Users/UserAvatarComponent.vue'
import ModalComponentUploadFile from '@/components/Modals/ModalComponentUploadFile.vue'

const route = useRoute()
const authStore = useAuthStore()
const serverSettingsStore = useServerSettingsStore()
const selectedActivityView = ref('userActivities')
const isLoading = ref(true)
const thisWeekDistances = ref([])
const thisMonthDistances = ref([])
const userGoals = ref(null)
const userNumberOfActivities = ref(0)
const userActivities = ref([])
const activityMediaMap = ref({})
const followedUserActivities = ref([])
const pageNumberUserActivities = ref(1)
const numRecords = serverSettingsStore.serverSettings.num_records_per_page || 25
const userHasMoreActivities = ref(true)
const { t } = useI18n()

async function fetchActivityMedia(activityId) {
  try {
    return await activityMedia.getUserActivityMediaByActivityId(activityId)
  } catch (error) {
    push.error(`${t('homeView.errorFetchingMedia')}: ${activityId} - ${error}`)
    return []
  }
}

async function fetchUserStars() {
  try {
    thisWeekDistances.value = await activities.getUserThisWeekStats(authStore.user.id)
    thisMonthDistances.value = await activities.getUserThisMonthStats(authStore.user.id)
    userGoals.value = await userGoalsService.getUserGoalResults()
  } catch (error) {
    // Set the error message
    push.error(`${t('homeView.errorFetchingUserStats')} - ${error}`)
  }
}

async function fetchMoreActivities() {
  // If the component is already loading or there are no more activities, return
  if (isLoading.value || !userHasMoreActivities.value) return

  try {
    // Add 1 to the page number
    pageNumberUserActivities.value++

    // Fetch the activities
    const newActivities = await activities.getUserActivitiesWithPagination(
      authStore.user.id,
      pageNumberUserActivities.value,
      numRecords
    )

    if (newActivities?.length) {
      if (!userActivities.value) {
        userActivities.value = []
      }
      userActivities.value = [...userActivities.value, ...newActivities]

      // Fetch media for each new activity
      for (const activity of newActivities) {
        activityMediaMap.value[activity.id] = await fetchActivityMedia(activity.id)
      }

      // Check if we've reached the end
      userHasMoreActivities.value = newActivities.length === numRecords
    } else {
      userHasMoreActivities.value = false
    }
  } catch (error) {
    // Set the error message
    push.error(`${t('homeView.errorFetchingUserActivities')} - ${error}`)
  }
}

const handleScroll = () => {
  // Get scroll position and page height more reliably
  const scrollPosition = window.scrollY + window.innerHeight
  const totalHeight = document.documentElement.scrollHeight

  // Trigger load when within 100px of bottom
  if (totalHeight - scrollPosition < 100) {
    fetchMoreActivities()
  }
}

const submitUploadFileForm = async (file) => {
  // Set the loading message
  const notification = push.promise(t('homeView.processingActivity'))

  // If there is a file, create the form data and upload the file
  if (file) {
    // Create the form data
    const formData = new FormData()
    formData.append('file', file)
    try {
      // Upload the file
      const createdActivities = await activities.uploadActivityFile(formData)
      // Fetch the new user activity
      if (!userActivities.value) {
        userActivities.value = []
      }
      for (const createdActivity of createdActivities) {
        userActivities.value.unshift(createdActivity)
        // Fetch media for the new activity
        activityMediaMap.value[createdActivity.id] = await fetchActivityMedia(createdActivity.id)
      }

      // Set the success message
      notification.resolve(t('homeView.successActivityAdded'))

      // Fetch the user stats
      fetchUserStars()

      // Fetch the user activities and user activities number
      userNumberOfActivities.value++
    } catch (error) {
      // Set the error message
      notification.reject(`${error}`)
    }
  }
}

async function refreshActivities() {
  // Set the loading message
  const notification = push.promise(t('homeView.refreshingActivities'))

  try {
    // Get the user activities
    const newActivities = await activities.getActivityRefresh()

    // If userActivities is not defined, do it
    if (!userActivities.value) {
      userActivities.value = []
    }

    // Iterate over the new activities and add them to the user activities
    if (newActivities) {
      for (const newActivity of newActivities) {
        userActivities.value.unshift(newActivity)
        // Fetch media for the new activity
        activityMediaMap.value[newActivity.id] = await fetchActivityMedia(newActivity.id)
      }

      // Set the user number of activities
      userNumberOfActivities.value += newActivities.length
    }

    // Set the success message
    notification.resolve(t('homeView.successActivitiesRefreshed'))

    // Fetch the user stats
    fetchUserStars()
  } catch (error) {
    // Set the error message
    notification.reject(`${error}`)
  }
}

function updateActivitiesOnDelete(activityId) {
  // Filter out the deleted activity from userActivities
  userActivities.value = userActivities.value.filter((activity) => activity.id !== activityId)
  // Set the activityDeleted value to true and show the success alert.
  push.success(t('homeView.successActivityDeleted'))
}

onMounted(async () => {
  if (route.query.activityFound === 'false') {
    // Set the activityFound value to false and show the error alert.
    push.error(t('homeView.errorActivityNotFound'))
  }

  if (route.query.activityDeleted === 'true') {
    updateActivitiesOnDelete(Number(route.query.activityId))
  }

  // Add the scroll event listener
  window.addEventListener('scroll', handleScroll)

  try {
    // Fetch the user stats
    fetchUserStars()

    // Fetch the user activities and user activities number
    userNumberOfActivities.value = await activities.getUserNumberOfActivities()

    // Fetch the initial user activities response (contains activities array and total_count)
    userActivities.value = await activities.getUserActivitiesWithPagination(
      authStore.user.id,
      pageNumberUserActivities.value,
      numRecords
    )

    // Fetch media for initial activities
    if (userActivities.value?.length) {
      for (const activity of userActivities.value) {
        activityMediaMap.value[activity.id] = await fetchActivityMedia(activity.id)
      }
    }

    followedUserActivities.value = await activities.getUserFollowersActivitiesWithPagination(
      authStore.user.id,
      pageNumberUserActivities.value,
      numRecords
    )

    // If the number of activities is greater than the page number times the number of records, there are no more activities
    if (pageNumberUserActivities.value * numRecords >= userNumberOfActivities.value) {
      userHasMoreActivities.value = false
    }
  } catch (error) {
    // Set the error message
    push.error(`${t('homeView.errorFetchingUserActivities')} - ${error}`)
  }

  isLoading.value = false
})

onUnmounted(() => {
  // Remove the scroll event listener
  window.removeEventListener('scroll', handleScroll)
})
</script>
