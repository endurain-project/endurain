<template>
  <div class="row">
    <!-- sidebar zone -->
    <div class="col-lg-3 col-md-12">
      <div class="mb-3 rounded p-3 bg-body-tertiary shadow-sm">
        <!-- user name and photo zone -->
        <div v-if="isLoading">
          <LoadingComponent />
        </div>
        <div v-else>
          <div class="justify-content-center d-flex" v-if="userProfile">
            <UserAvatarComponent :user="userProfile" :width="120" :height="120" />
          </div>
          <div class="text-center mt-3 fw-bold" v-if="userProfile.id">
            <h3>
              <span>{{ userProfile.name }}</span>
            </h3>
            <span class="fw-lighter"> @{{ userProfile.username }} </span>
            <br />
            <span class="fw-lighter" v-if="userProfile.city">
              <font-awesome-icon :icon="['fas', 'location-dot']" />
              {{ userProfile.city }}
            </span>
          </div>
        </div>
      </div>
      <!-- followers and number of activities -->
      <div class="mb-3 rounded p-3 bg-body-tertiary shadow-sm">
        <div class="vstack d-flex align-middle text-center">
          <span class="fw-lighter">
            {{ $t('userView.thisMonthActivitiesNumber') }}
          </span>
          <h1>
            {{ thisMonthNumberOfActivities }}
          </h1>
          <div class="row align-items-center">
            <div class="col">
              {{ followingCountAccepted }}
              <br />
              <span class="fw-lighter">
                {{ $t('userView.userFollowing') }}
              </span>
            </div>
            <div class="col">
              {{ followersCountAccepted }}
              <br />
              <span class="fw-lighter">
                {{ $t('userView.userFollowers') }}
              </span>
            </div>
          </div>
        </div>
      </div>
      <!-- user stats zone -->
      <div class="mb-3 rounded p-3 bg-body-tertiary shadow-sm">
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
      <!-- user goals zone -->
      <div
        class="mb-3 rounded p-3 bg-body-tertiary shadow-sm"
        v-if="userProfile && userProfile.id == authStore.user.id"
      >
        <div v-if="isLoading">
          <LoadingComponent />
        </div>
        <UserGoalsStatsComponent :goals="userGoals" v-else />
      </div>
    </div>
    <!-- content zone -->
    <div class="col">
      <div class="mb-3 rounded pb-3 bg-body-tertiary shadow-sm">
        <div v-if="isLoading">
          <LoadingComponent />
        </div>
        <!-- navigation zone-->
        <ul class="nav nav-pills justify-content-center" id="pills-tab" role="tablist">
          <li class="nav-item" role="presentation">
            <button
              class="nav-link active link-body-emphasis mt-3"
              id="pills-activities-tab"
              data-bs-toggle="pill"
              data-bs-target="#pills-activities"
              type="button"
              role="tab"
              aria-controls="pills-activities"
              aria-selected="true"
            >
              {{ $t('userView.navigationActivities') }}
            </button>
          </li>
          <li class="nav-item" role="presentation">
            <button
              class="nav-link link-body-emphasis mt-3"
              id="pills-following-tab"
              data-bs-toggle="pill"
              data-bs-target="#pills-following"
              type="button"
              role="tab"
              aria-controls="pills-following"
              aria-selected="false"
            >
              {{ $t('userView.navigationFollowing') }}
            </button>
          </li>
          <li class="nav-item" role="presentation">
            <button
              class="nav-link link-body-emphasis mt-3"
              id="pills-followers-tab"
              data-bs-toggle="pill"
              data-bs-target="#pills-followers"
              type="button"
              role="tab"
              aria-controls="pills-followers"
              aria-selected="false"
            >
              {{ $t('userView.navigationFollowers') }}
            </button>
          </li>
          <li
            class="nav-item"
            role="presentation"
            v-if="userProfile && userProfile.id == authStore.user.id"
          >
            <router-link
              :to="{ name: 'settings', query: { profileSettings: 1 } }"
              class="btn nav-link link-body-emphasis mt-3"
            >
              <font-awesome-icon :icon="['fas', 'fa-gear']" />
              {{ $t('userView.navigationUserSettings') }}
            </router-link>
          </li>
          <li
            class="nav-item"
            role="presentation"
            v-if="userProfile && userProfile.id != authStore.user.id && userFollowState == null"
          >
            <!-- Follow user button -->
            <a
              class="btn btn-outline-success ms-2 mt-3"
              href="#"
              role="button"
              data-bs-toggle="modal"
              data-bs-target="#followUserModal"
            >
              <font-awesome-icon :icon="['fas', 'fa-user-plus']" />
              {{ $t('userView.navigationFollow') }}
            </a>

            <!-- Modal follow user -->
            <ModalComponent
              modalId="followUserModal"
              :title="t('userView.modalFollowUserTitle')"
              :body="`${t('userView.modalFollowUserBody')}<b>${userProfile.name}</b>?`"
              :actionButtonType="`success`"
              :actionButtonText="t('userView.modalFollowUserTitle')"
              @submitAction="submitFollowUser"
            />
          </li>
          <li
            class="nav-item"
            role="presentation"
            v-if="
              userProfile &&
              userProfile.id != authStore.user.id &&
              userFollowState != null &&
              !userFollowState.is_accepted
            "
          >
            <!-- Cancel follow request button -->
            <a
              class="btn btn-outline-secondary ms-2 mt-3"
              href="#"
              role="button"
              data-bs-toggle="modal"
              data-bs-target="#cancelFollowUserModal"
            >
              <font-awesome-icon :icon="['fas', 'fa-user-plus']" />
              {{ $t('userView.navigationRequestSent') }}
            </a>

            <!-- Modal cancel follow request -->
            <ModalComponent
              modalId="cancelFollowUserModal"
              :title="t('userView.modalCancelFollowRequestTitle')"
              :body="`${t('userView.modalCancelFollowRequestBody')}<b>${userProfile.name}</b>?`"
              :actionButtonType="`danger`"
              :actionButtonText="t('userView.modalCancelFollowRequestTitle')"
              @submitAction="submitCancelFollowUser"
            />
          </li>
          <li
            class="nav-item"
            role="presentation"
            v-if="
              userProfile &&
              userProfile.id != authStore.user.id &&
              userFollowState != null &&
              userFollowState.is_accepted
            "
          >
            <!-- Unfollow user button -->
            <a
              class="btn btn-outline-danger ms-2 mt-3"
              href="#"
              role="button"
              data-bs-toggle="modal"
              data-bs-target="#unfollowUserModal"
            >
              <font-awesome-icon :icon="['fas', 'fa-user-minus']" />
              {{ $t('userView.navigationUnfollow') }}
            </a>

            <!-- Modal unfollow user -->
            <ModalComponent
              modalId="unfollowUserModal"
              :title="t('userView.modalUnfollowUserTitle')"
              :body="`${t('userView.modalUnfollowUserBody')}<b>${userProfile.name}</b>?`"
              :actionButtonType="`danger`"
              :actionButtonText="t('userView.modalUnfollowUserTitle')"
              @submitAction="submitUnfollowUser"
            />
          </li>
        </ul>
      </div>
      <div v-if="isLoading">
        <LoadingComponent />
      </div>
      <div class="tab-content" id="pills-tabContent" v-else>
        <!-- activities tab content -->
        <div
          class="tab-pane fade show active"
          id="pills-activities"
          role="tabpanel"
          aria-labelledby="pills-activities-tab"
          tabindex="0"
        >
          <!-- pagination -->
          <nav class="mb-3 rounded pt-3 pb-1 px-3 bg-body-tertiary shadow-sm">
            <ul class="pagination justify-content-center">
              <li :class="['page-item', { active: week === 0 }]">
                <a href="#" class="page-link link-body-emphasis" @click="setWeek(0, $event)">
                  {{ $t('userView.activitiesPaginationWeek0') }}
                </a>
              </li>
              <li v-if="week > 2" class="page-item disabled">
                <a class="page-link">...</a>
              </li>
              <li v-for="i in visibleWeeks" :key="i" :class="['page-item', { active: i === week }]">
                <a href="#" class="page-link link-body-emphasis" @click="setWeek(i, $event)">
                  {{ formatDateRange(i) }}
                </a>
              </li>
              <li v-if="week < 49" class="page-item disabled">
                <a class="page-link">...</a>
              </li>
              <li :class="['page-item', { active: week === 51 }]">
                <a href="#" class="page-link link-body-emphasis" @click="setWeek(51, $event)">
                  {{ $t('userView.activitiesPaginationWeek51') }}
                </a>
              </li>
            </ul>
          </nav>

          <!-- Checking if userWeekActivities is loaded and has length -->
          <div v-if="userWeekActivities && userWeekActivities.length">
            <!-- Iterating over userWeekActivities to display them -->
            <div
              class="card mb-3 rounded border-0 bg-body-tertiary shadow-sm"
              v-for="activity in userWeekActivities"
              :key="activity.id"
            >
              <div class="card-body">
                <ActivitySummaryComponent
                  :activity="activity"
                  :source="'home'"
                  :units="userProfile.units"
                />
              </div>
              <ActivityMapComponent
                class="mx-3 mb-3"
                :activity="activity"
                :source="'home'"
                v-if="
                  activity &&
                  ((authStore.isAuthenticated && authStore.user.id === activity.user_id) ||
                    (activity.hide_map === false && authStore.isAuthenticated === false))
                "
              />
            </div>
          </div>
          <!-- Displaying a message or component when there are no activities -->
          <NoItemsFoundComponent :show-shadow="false" v-else />
        </div>

        <!-- following tab content -->
        <div
          class="tab-pane fade"
          id="pills-following"
          role="tabpanel"
          aria-labelledby="pills-following-tab"
          tabindex="0"
        >
          <ul
            class="list-group list-group-flush w-100 rounded shadow-sm"
            v-if="followersAll && followersAll.length"
          >
            <li
              class="list-group-item d-flex justify-content-center align-items-center w-100 p-3 bg-body-tertiary"
              v-for="follower in followersAll"
              :key="follower.following_id"
            >
              <FollowersListComponent
                :follower="follower"
                :type="1"
                @followingDeleted="updateFollowingList"
              />
            </li>
          </ul>
          <!-- Displaying a message or component when there are no following users -->
          <NoItemsFoundComponent :show-shadow="false" v-else />
        </div>

        <!-- followers tab content -->
        <div
          class="tab-pane fade"
          id="pills-followers"
          role="tabpanel"
          aria-labelledby="pills-followers-tab"
          tabindex="0"
        >
          <ul
            class="list-group list-group-flush w-100 rounded shadow-sm"
            v-if="followingAll && followingAll.length"
          >
            <li
              class="list-group-item d-flex justify-content-center align-items-center w-100 p-3 bg-body-tertiary"
              v-for="follower in followingAll"
              :key="follower.follower_id"
            >
              <FollowersListComponent
                :follower="follower"
                :type="2"
                @followerDeleted="updateFollowerList"
                @followerAccepted="updateFollowerListWithAccepted"
              />
            </li>
          </ul>
          <!-- Displaying a message or component when there are no following users -->
          <NoItemsFoundComponent :show-shadow="false" v-else />
        </div>
      </div>
    </div>

    <!-- back button -->
    <BackButtonComponent />
  </div>
</template>

<script setup>
import { ref, onMounted, computed, watch } from 'vue'
import { useRoute } from 'vue-router'
import { useI18n } from 'vue-i18n'
// Importing the stores
import { useAuthStore } from '@/stores/authStore'
// Importing the services
import { users } from '@/services/usersService'
import { activities } from '@/services/activitiesService'
import { followers } from '@/services/followersService'
import { userGoals as userGoalsService } from '@/services/userGoalsService'
// Import Notivue push
import { push } from 'notivue'
// Importing the components
import UserDistanceStatsComponent from '@/components/Users/UserDistanceStatsComponent.vue'
import UserGoalsStatsComponent from '@/components/Users/UserGoalsStatsComponent.vue'
import LoadingComponent from '@/components/GeneralComponents/LoadingComponent.vue'
import NoItemsFoundComponent from '@/components/GeneralComponents/NoItemsFoundComponents.vue'
import ActivitySummaryComponent from '@/components/Activities/ActivitySummaryComponent.vue'
import ActivityMapComponent from '@/components/Activities/ActivityMapComponent.vue'
import FollowersListComponent from '@/components/Followers/FollowersListComponent.vue'
import BackButtonComponent from '@/components/GeneralComponents/BackButtonComponent.vue'
import UserAvatarComponent from '@/components/Users/UserAvatarComponent.vue'
import ModalComponent from '@/components/Modals/ModalComponent.vue'

const { t } = useI18n()
const authStore = useAuthStore()
const route = useRoute()
const userProfile = ref(null)
const userGoals = ref(null)
const thisWeekDistances = ref([])
const thisMonthDistances = ref([])
const thisMonthNumberOfActivities = ref(0)
const followersCountAccepted = ref(0)
const followingCountAccepted = ref(0)
const followersAll = ref([])
const followingAll = ref([])
const isLoading = ref(true)
const isActivitiesLoading = ref(true)
const week = ref(0)
const totalWeeks = 50
const weekRange = 1
const visibleWeeks = computed(() => {
  const start = Math.max(1, week.value - weekRange)
  const end = Math.min(totalWeeks, week.value + weekRange)
  return Array.from({ length: end - start + 1 }, (_, i) => i + start)
})
const userWeekActivities = ref([])
const userFollowState = ref(null)

async function fetchUserStars() {
  try {
    thisWeekDistances.value = await activities.getUserThisWeekStats(authStore.user.id)
    thisMonthDistances.value = await activities.getUserThisMonthStats(authStore.user.id)
  } catch (error) {
    // Set the error message
    push.error(`${t('userView.errorFetchingUserStats')} - ${error}`)
  }
}

async function fetchUserFollowers() {
  try {
    // Fetch the user followers and following count
    followersCountAccepted.value = await followers.getUserFollowingCountAccepted(route.params.id)
    followingCountAccepted.value = await followers.getUserFollowersCountAccepted(route.params.id)

    // Fetch the user followers and following accepted count
    if (Number(route.params.id) === authStore.user.id) {
      // Fetch the user followers and following
      followersAll.value = await followers.getUserFollowingAll(authStore.user.id)
      followingAll.value = await followers.getUserFollowersAll(authStore.user.id)
    } else {
      // Fetch the user followers and following
      followersAll.value = await followers.getUserFollowersAll(authStore.user.id)
      followingAll.value = await followers.getUserFollowingAll(authStore.user.id)
    }
  } catch (error) {
    // Set the error message
    push.error(`${t('userView.errorFetchingUserFollowers')} - ${error}`)
  }
}

const fetchData = async () => {
  isLoading.value = true
  isActivitiesLoading.value = true
  week.value = 0
  try {
    // Fetch the user profile
    userProfile.value = await users.getUserById(route.params.id)

    // Fetch the user stats
    await fetchUserStars()

    // Fetch the user number of activities for this month
    thisMonthNumberOfActivities.value = await activities.getUserThisMonthActivitiesNumber(
      route.params.id
    )

    await fetchUserFollowers()

    // Fetch the user week activities
    userWeekActivities.value = await activities.getUserWeekActivities(route.params.id, week.value)

    // Fetch the user follow state
    if (Number(route.params.id) !== authStore.user.id) {
      userFollowState.value = await followers.getUserFollowState(authStore.user.id, route.params.id)
    } else {
      userGoals.value = await userGoalsService.getUserGoalResults()
    }
  } catch (error) {
    push.error(`${t('userView.errorFetchingUserActivities')} - ${error}`)
  }
  isLoading.value = false
  isActivitiesLoading.value = false
}

onMounted(async () => {
  await fetchData()
  if (route.query.tab === 'followers') {
    // Get the followers tab button element and click it
    const followersTabButton = document.getElementById('pills-followers-tab')
    if (followersTabButton) {
      followersTabButton.click()
    }
  }
})

watch(() => route.params.id, fetchData)

function formatDateRange(weekNumber) {
  const today = new Date()
  const currentDay = today.getDay()
  const daysToMonday = currentDay === 0 ? -6 : 1 - currentDay // Adjusting for when Sunday is day 0

  const startOfWeek = new Date(today)
  startOfWeek.setDate(today.getDate() + daysToMonday - weekNumber * 7)

  const endOfWeek = new Date(startOfWeek)
  endOfWeek.setDate(startOfWeek.getDate() + 6) // Set to Sunday of the same week

  const format = (date) =>
    `${date.getDate().toString().padStart(2, '0')}/${(date.getMonth() + 1).toString().padStart(2, '0')}`

  return `${format(startOfWeek)}-${format(endOfWeek)}`
}

async function setWeek(newWeek, event) {
  isActivitiesLoading.value = true
  event.preventDefault()
  week.value = newWeek

  try {
    userWeekActivities.value = await activities.getUserWeekActivities(
      userProfile.value.id,
      week.value
    )
  } catch (error) {
    // Set the error message
    push.error(`${t('userView.errorFetchingUserActivities')} - ${error}`)
  } finally {
    isActivitiesLoading.value = false
  }
}

function updateFollowingList(deletedFollowingId) {
  // will get the follower to remove
  const auxFollower = followersAll.value.find(
    (follower) => follower.following_id === deletedFollowingId
  )

  // if the follower is accepted, will decrease the count
  if (auxFollower.is_accepted) {
    followingCountAccepted.value -= 1
  }

  // will remove the follower from the list
  followersAll.value = followersAll.value.filter(
    (follower) => follower.following_id !== deletedFollowingId
  )
  push.success(t('userView.successFollowingDeleted'))
}

function updateFollowerList(deletedFollowerId) {
  if (authStore.user.id !== userProfile.value.id) {
    // will get the following to remove
    const auxFollowing = followingAll.value.find(
      (follower) => follower.following_id === deletedFollowerId
    )

    // if the following is accepted, will decrease the count
    if (auxFollowing.is_accepted) {
      followingCountAccepted.value -= 1
    }

    // will remove the following from the list
    followingAll.value = followingAll.value.filter(
      (follower) => follower.following_id !== deletedFollowerId
    )
    push.success(t('userView.successFollowerDeleted'))
  } else {
    // will get the following to remove
    const auxFollowing = followingAll.value.find(
      (follower) => follower.follower_id === deletedFollowerId
    )

    // if the following is accepted, will decrease the count
    if (auxFollowing.is_accepted) {
      followersCountAccepted.value -= 1
    }

    // will remove the following from the list
    followingAll.value = followingAll.value.filter(
      (follower) => follower.follower_id !== deletedFollowerId
    )
    push.success(t('userView.successFollowerDeleted'))
  }
}

function updateFollowerListWithAccepted(acceptedFollowerId) {
  // will get the following to change the is_accepted
  followingAll.value = followingAll.value.map((follower) => {
    if (follower.follower_id === acceptedFollowerId) {
      follower.is_accepted = true
    }
    return follower
  })

  // will increase the count
  followersCountAccepted.value += 1

  // Set the success message
  push.success(t('userView.successFollowerAccepted'))
}

async function submitFollowUser() {
  try {
    // Create the user follow
    const newFollower = await followers.createUserFollowsSpecificUser(userProfile.value.id)

    // Add the user to the following list
    followingAll.value.unshift(newFollower)

    // Set the follower state
    userFollowState.value = 0

    // Set the success message
    push.success(t('userView.successFollowRequestSent'))
  } catch (error) {
    // Set the error message
    push.error(`${t('user.errorUnableToSendFollow')} - ${error}`)
  }
}

async function unfollowUser() {
  // Delete the user follow
  await followers.deleteUserFollower(userProfile.value.id)

  // Remove the user from the following list
  followingAll.value = followingAll.value.filter(
    (follower) => follower.following_id !== userProfile.value.id
  )

  // Decrease the following count
  userFollowState.value = null
}

async function submitCancelFollowUser() {
  try {
    // Call the unfollowUser function
    await unfollowUser()

    // Set the success message
    push.success(t('userView.successFollowRequestCancelled'))
  } catch (error) {
    // Set the error message
    push.error(`${t('userView.errorUnableToSendFollow')} - ${error}`)
  }
}

async function submitUnfollowUser() {
  try {
    // Call the unfollowUser function
    await unfollowUser()

    // Decrease the following count
    followingCountAccepted.value -= 1

    // Set the success message
    push.success(t('userView.successUserUnfollowed'))
  } catch (error) {
    // Set the error message
    push.error(`${t('userView.errorUnableToUnfollow')} - ${error}`)
  }
}
</script>
