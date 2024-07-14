<template>
    <div class="row align-items-center">
        <!-- picture col -->
        <div class="col">
            <div v-if="isLoading">
                <LoadingComponent />
            </div>
            <div class="vstack d-flex justify-content-center" v-else>
                <div class="d-flex justify-content-center" v-if="userProfile">
                    <UserAvatarComponent :userProp="userProfile" :width=120 :height=120 />
                </div>
                <div class="text-center mt-3 mb-3" v-if="userProfile">
                    <h3>
                        <span>{{ userProfile.name }}</span>
                    </h3>
                    <span class="fw-lighter" v-if="userProfile.city">
                        <font-awesome-icon :icon="['fas', 'location-dot']" />
                        {{ userProfile.city }}
                    </span>
                </div>
            </div>
        </div>
        <div class="col">
            <div v-if="isLoading">
                <LoadingComponent />
            </div>
            <div class="vstack d-flex align-middle text-center" v-else>
                <span class="fw-lighter">
                    {{ $t("user.thisMonthActivitiesNumber") }}
                </span>
                <h1>
                    {{ thisMonthNumberOfActivities }}
                </h1>
                <div class="row align-items-center">
                    <div class="col">
                        {{ followingCountAccepted }}
                        <br>
                        <span class="fw-lighter">
                            {{ $t("user.userFollowing") }}
                        </span>
                    </div>
                    <div class="col">
                        {{ followersCountAccepted }}
                        <br>
                        <span class="fw-lighter">
                            {{ $t("user.userFollowers") }}
                        </span>
                    </div>
                </div>
            </div>
        </div>
        <div class="col-sm">
            <div v-if="isLoading">
                <LoadingComponent />
            </div>
            <UserDistanceStatsComponent :thisWeekDistances="thisWeekDistances" :thisMonthDistances="thisMonthDistances" v-else />
        </div>
    </div>

    <!-- navigation -->
    <div v-if="isLoading">
        <LoadingComponent />
    </div>
    <ul class="nav nav-pills mb-3 justify-content-center" id="pills-tab" role="tablist" v-else-if="userProfile">
        <li class="nav-item" role="presentation">
            <button class="nav-link active link-body-emphasis" id="pills-activities-tab" data-bs-toggle="pill"
                data-bs-target="#pills-activities" type="button" role="tab" aria-controls="pills-activities"
                aria-selected="true">
                {{ $t("user.navigationActivities") }}
            </button>
        </li>
        <li class="nav-item" role="presentation">
            <button class="nav-link link-body-emphasis" id="pills-following-tab" data-bs-toggle="pill"
                data-bs-target="#pills-following" type="button" role="tab" aria-controls="pills-following"
                aria-selected="false">
                {{ $t("user.navigationFollowing") }}
            </button>
        </li>
        <li class="nav-item" role="presentation">
            <button class="nav-link link-body-emphasis" id="pills-followers-tab" data-bs-toggle="pill"
                data-bs-target="#pills-followers" type="button" role="tab" aria-controls="pills-followers"
                aria-selected="false">
                {{ $t("user.navigationFollowers") }}
            </button>
        </li>
        <li class="nav-item" role="presentation" v-if="userProfile.id == authStore.user.id">
            <router-link :to="{ name: 'settings', query: { profileSettings: 1 }}" class="btn nav-link link-body-emphasis">
                <font-awesome-icon :icon="['fas', 'fa-gear']" />
                {{ $t("user.navigationUserSettings") }}
            </router-link>
        </li>
        <li class="nav-item" role="presentation" v-if="userProfile.id != authStore.user.id && userFollowState == null">
            <!-- Follow user button -->
            <a class="btn btn-outline-success h-100 ms-2" href="#" role="button" data-bs-toggle="modal"
                data-bs-target="#followUserModal">
                <font-awesome-icon :icon="['fas', 'fa-user-plus']" />
                {{ $t("user.navigationFollow") }}
            </a>

            <!-- Modal follow user -->
            <div class="modal fade" id="followUserModal" tabindex="-1" aria-labelledby="followUserModal" aria-hidden="true">
                <div class="modal-dialog">
                    <div class="modal-content">
                        <div class="modal-header">
                            <h1 class="modal-title fs-5" id="followUserModal">
                                {{ $t("user.modalFollowUserTitle") }}
                            </h1>
                            <button type="button" class="btn-close" data-bs-dismiss="modal" aria-label="Close"></button>
                        </div>
                        <div class="modal-body">
                            {{ $t("user.modalFollowUserBody") }}<b>{{ userProfile.name }}</b>?
                        </div>
                        <div class="modal-footer">
                            <button type="button" class="btn btn-secondary" data-bs-dismiss="modal">
                                {{ $t("generalItens.buttonClose") }}
                            </button>
                            <a type="button" class="btn btn-success" data-bs-dismiss="modal" @click="submitFollowUser">
                                {{ $t("user.modalFollowUserTitle") }}
                            </a>
                        </div>
                    </div>
                </div>
            </div>
        </li>
        <li class="nav-item" role="presentation" v-if="userProfile.id != authStore.user.id && userFollowState != null && !userFollowState.is_accepted">
            <!-- Cancel follow request button -->
            <a class="btn btn-outline-secondary h-100 ms-2" href="#" role="button" data-bs-toggle="modal"
                data-bs-target="#cancelFollowUserModal">
                <font-awesome-icon :icon="['fas', 'fa-user-plus']" />
                {{ $t("user.navigationRequestSent") }}
            </a>

            <!-- Modal cancel follow request -->
            <div class="modal fade" id="cancelFollowUserModal" tabindex="-1" aria-labelledby="cancelFollowUserModal" aria-hidden="true">
                <div class="modal-dialog">
                    <div class="modal-content">
                        <div class="modal-header">
                            <h1 class="modal-title fs-5" id="cancelFollowUserModal">
                                {{ $t("user.modalCancelFollowRequestTitle") }}
                            </h1>
                            <button type="button" class="btn-close" data-bs-dismiss="modal" aria-label="Close"></button>
                        </div>
                        <div class="modal-body">
                            {{ $t("user.modalCancelFollowRequestBody") }}<b>{{ userProfile.name }}</b>?
                        </div>
                        <div class="modal-footer">
                            <button type="button" class="btn btn-secondary" data-bs-dismiss="modal">
                                {{ $t("generalItens.buttonClose") }}
                            </button>
                            <a type="button" class="btn btn-danger" data-bs-dismiss="modal" @click="submitCancelFollowUser">
                                {{ $t("user.modalCancelFollowRequestTitle") }}
                            </a>
                        </div>
                    </div>
                </div>
            </div>
        </li>
        <li class="nav-item" role="presentation" v-if="userProfile.id != authStore.user.id && userFollowState != null && userFollowState.is_accepted">
            <!-- Unfollow user button -->
            <a class="btn btn-outline-danger h-100 ms-2" href="#" role="button" data-bs-toggle="modal"
                data-bs-target="#unfollowUserModal">
                <font-awesome-icon :icon="['fas', 'fa-user-minus']" />
                {{ $t("user.navigationUnfollow") }}
            </a>

            <!-- Modal unfollow user -->
            <div class="modal fade" id="unfollowUserModal" tabindex="-1" aria-labelledby="unfollowUserModal" aria-hidden="true">
                <div class="modal-dialog">
                    <div class="modal-content">
                        <div class="modal-header">
                            <h1 class="modal-title fs-5" id="unfollowUserModal">
                                {{ $t("user.modalUnfollowUserTitle") }}
                            </h1>
                            <button type="button" class="btn-close" data-bs-dismiss="modal" aria-label="Close"></button>
                        </div>
                        <div class="modal-body">
                            {{ $t("user.modalUnfollowUserBody") }}<b>{{ userProfile.name }}</b>?
                        </div>
                        <div class="modal-footer">
                            <button type="button" class="btn btn-secondary" data-bs-dismiss="modal">
                                {{ $t("generalItens.buttonClose") }}
                            </button>
                            <a type="button" class="btn btn-danger" data-bs-dismiss="modal" @click="submitUnfollowUser">
                                {{ $t("user.modalUnfollowUserTitle") }}
                            </a>
                        </div>
                    </div>
                </div>
            </div>
        </li>
    </ul>

    <div v-if="isLoading">
        <LoadingComponent />
    </div>
    <div class="tab-content" id="pills-tabContent" v-else>
        <!-- activities tab content -->
        <div class="tab-pane fade show active" id="pills-activities" role="tabpanel" aria-labelledby="pills-activities-tab" tabindex="0">
            <!-- pagination -->
            <nav>
                <ul class="pagination justify-content-center">
                    <li :class="['page-item', { active: week === 0 }]" >
                        <a href="#" class="page-link link-body-emphasis" @click="setWeek(0, $event)">
                            {{ $t("user.activitiesPaginationWeek0") }}
                        </a>
                    </li>
                    <li v-if="week > 2" class="page-item disabled">
                        <a class="page-link">...</a>
                    </li>
                    <li v-for="i in visibleWeeks" :key="i" :class="['page-item', { active: i === week }]" >
                        <a href="#" class="page-link link-body-emphasis" @click="setWeek(i, $event)">
                            {{ formatDateRange(i) }}
                        </a>
                    </li>
                    <li v-if="week < 49" class="page-item disabled">
                        <a class="page-link">...</a>
                    </li>
                    <li :class="['page-item', { active: week === 51 }]" >
                        <a href="#" class="page-link link-body-emphasis" @click="setWeek(51, $event)">
                            {{ $t("user.activitiesPaginationWeek51") }}
                        </a>
                    </li>
                </ul>
            </nav>

            <!-- Checking if userWeekActivities is loaded and has length -->
            <div v-if="userWeekActivities && userWeekActivities.length">
            <!-- Iterating over userWeekActivities to display them -->
                <div class="card mb-3" v-for="activity in userWeekActivities" :key="activity.id">
                    <div class="card-body">
                        <ActivitySummaryComponent :activity="activity" :source="'home'"/>
                    </div>
                    <ActivityMapComponent class="mx-3 mb-3" :activity="activity" :source="'home'"/>
                </div>
            </div>
            <!-- Displaying a message or component when there are no activities -->
            <NoItemsFoundComponent v-else />
        </div>

        <!-- following tab content -->
        <div class="tab-pane fade" id="pills-following" role="tabpanel" aria-labelledby="pills-following-tab" tabindex="0">
            <ul class="list-group list-group-flush align-items-center" v-if="followersAll && followersAll.length">
                <li class="list-group-item d-flex justify-content-between" v-for="follower in followersAll" :key="follower.following_id">
                    <FollowersListComponent :follower="follower" :type="1" @followingDeleted="updateFollowingList"/>
                </li>
            </ul>
            <!-- Displaying a message or component when there are no following users -->
            <NoItemsFoundComponent v-else />
        </div>

        <!-- followers tab content -->
        <div class="tab-pane fade" id="pills-followers" role="tabpanel" aria-labelledby="pills-followers-tab" tabindex="0">
            <ul class="list-group list-group-flush align-items-center" v-if="followingAll && followingAll.length">
                <li class="list-group-item d-flex justify-content-between" v-for="follower in followingAll" :key="follower.follower_id">
                    <FollowersListComponent :follower="follower" :type="2" @followerDeleted="updateFollowerList" @followerAccepted="updateFollowerListWithAccepted"/>
                </li>
            </ul>
            <!-- Displaying a message or component when there are no following users -->
            <NoItemsFoundComponent v-else />
        </div>
    </div>

    <!-- back button -->
    <BackButtonComponent />
</template>

<script>
import { ref, onMounted, computed, watch } from 'vue';
import { useRoute } from 'vue-router';
import { useI18n } from 'vue-i18n';
// Importing the stores
import { useAuthStore } from '@/stores/authStore';
// Importing the services
import { users } from '@/services/usersService';
import { activities } from '@/services/activitiesService';
import { followers } from '@/services/followersService';
// Importing the utils
import { addToast } from '@/utils/toastUtils';
// Importing the components
import UserDistanceStatsComponent from '@/components/Activities/UserDistanceStatsComponent.vue';
import LoadingComponent from '@/components/GeneralComponents/LoadingComponent.vue';
import NoItemsFoundComponent from '@/components/GeneralComponents/NoItemsFoundComponents.vue';
import ActivitySummaryComponent from '@/components/Activities/ActivitySummaryComponent.vue';
import ActivityMapComponent from '@/components/Activities/ActivityMapComponent.vue';
import FollowersListComponent from '@/components/Followers/FollowersListComponent.vue';
import BackButtonComponent from '@/components/GeneralComponents/BackButtonComponent.vue';
import UserAvatarComponent from '@/components/Users/UserAvatarComponent.vue';

export default {
    components: {
        UserDistanceStatsComponent,
        NoItemsFoundComponent,
        LoadingComponent,
        ActivitySummaryComponent,
        ActivityMapComponent,
        FollowersListComponent,
        BackButtonComponent,
        UserAvatarComponent,
    },
    setup () {
        const authStore = useAuthStore();
        const route = useRoute();
        const userProfile = ref(null);
        const thisWeekDistances = ref([]);
        const thisMonthDistances = ref([]);
        const thisMonthNumberOfActivities = ref(0);
        const followersCountAccepted = ref(0);
        const followingCountAccepted = ref(0);
        const followersAll = ref([]);
        const followingAll = ref([]);
        const isLoading = ref(true);
        const isActivitiesLoading = ref(true);
        const { t } = useI18n();
        const week = ref(0);
        const totalWeeks = 50;
        const weekRange = 1;
        const visibleWeeks = computed(() => {
            let start = Math.max(1, week.value - weekRange);
            let end = Math.min(totalWeeks, week.value + weekRange);
            return Array.from({ length: end - start + 1 }, (_, i) => i + start);
        });
        const userWeekActivities = ref([]);
        const userFollowState = ref(null);

        async function fetchUserStars() {
            try {
                thisWeekDistances.value = await activities.getUserThisWeekStats(authStore.user.id);
                thisMonthDistances.value = await activities.getUserThisMonthStats(authStore.user.id);
            } catch (error) {
                // Set the error message
                addToast(t('generalItens.errorFetchingInfo'), 'danger', true);
            }
        }

        const fetchData = async () => {
            isLoading.value = true;
            isActivitiesLoading.value = true;
            week.value = 0;
            try {
                // Fetch the user profile
                userProfile.value = await users.getUserById(route.params.id);

                // Fetch the user stats
                await fetchUserStars();

                // Fetch the user number of activities for this month
                thisMonthNumberOfActivities.value = await activities.getUserThisMonthActivitiesNumber(route.params.id);

                // Fetch the user followers and following accepted count
                if (route.params.id == authStore.user.id) {
                    followersCountAccepted.value = await followers.getUserFollowingCountAccepted(route.params.id);
                    followingCountAccepted.value = await followers.getUserFollowersCountAccepted(route.params.id);
                } else {
                    followersCountAccepted.value = await followers.getUserFollowersCountAccepted(route.params.id);
                    followingCountAccepted.value = await followers.getUserFollowingCountAccepted(route.params.id);

                }

                // Fetch the user followers and following
                if (route.params.id == authStore.user.id) {
                    followersAll.value = await followers.getUserFollowingAll(authStore.user.id);
                    followingAll.value = await followers.getUserFollowersAll(authStore.user.id);
                } else {
                    followersAll.value = await followers.getUserFollowersAll(authStore.user.id);
                    followingAll.value = await followers.getUserFollowingAll(authStore.user.id);
                }

                // Fetch the user week activities
                userWeekActivities.value = await activities.getUserWeekActivities(route.params.id, week.value);

                // Fetch the user follow state
                if (route.params.id != authStore.user.id) {
                    userFollowState.value = await followers.getUserFollowState(authStore.user.id, route.params.id);
                }
            } catch (error) {
                addToast(t('generalItens.errorFetchingInfo') + " - " + error.toString(), 'danger', true);
            }
            isLoading.value = false;
            isActivitiesLoading.value = false;
        };

        onMounted(fetchData);

        watch(() => route.params.id, fetchData);

        function formatDateRange(weekNumber) {
            const today = new Date();
            const currentDay = today.getDay();
            const daysToMonday = currentDay === 0 ? -6 : 1 - currentDay;  // Adjusting for when Sunday is day 0

            const startOfWeek = new Date(today);
            startOfWeek.setDate(today.getDate() + daysToMonday - (weekNumber * 7));

            const endOfWeek = new Date(startOfWeek);
            endOfWeek.setDate(startOfWeek.getDate() + 6);  // Set to Sunday of the same week

            const format = (date) => `${date.getDate().toString().padStart(2, '0')}/${(date.getMonth() + 1).toString().padStart(2, '0')}`;

            return `${format(startOfWeek)}-${format(endOfWeek)}`;
        }

        async function setWeek(newWeek, event) {
            isActivitiesLoading.value = true;
            event.preventDefault();
            week.value = newWeek;

            try{
                userWeekActivities.value = await activities.getUserWeekActivities(userProfile.value.id, week.value);
            } catch (error) {
                // Set the error message
                addToast(t('generalItens.errorEditingInfo') + " - " + error.toString(), 'danger', true);
            } finally {
                isActivitiesLoading.value = false;
            }
        }

        function updateFollowingList(deletedFollowingId) {
            followingAll.value = followingAll.value.filter(follower => follower.following_id !== deletedFollowingId);
            followersCountAccepted.value -= 1;
            addToast(t('user.successFollowingDeleted'), 'success', true);
        }

        function updateFollowerList(deletedFollowerId){
            followersAll.value = followersAll.value.filter(follower => follower.follower_id !== deletedFollowerId);
            followingCountAccepted.value -= 1;
            addToast(t('user.successFollowerDeleted'), 'success', true);
        }

        function updateFollowerListWithAccepted(acceptedFollowerId){
            followersAll.value = followersAll.value.map(follower => {
                if (follower.follower_id === acceptedFollowerId) {
                    follower.is_accepted = true;
                }
                return follower;
            });
            followingCountAccepted.value += 1;
            addToast(t('user.successFollowerAccepted'), 'success', true);
        }

        async function submitFollowUser() {
            try{
                await followers.createUserFollowsSpecificUser(authStore.user.id, userProfile.value.id);

                userFollowState.value = 0;

                // Set the success message
                addToast(t('user.successFollowRequestSent'), 'success', true);
            } catch (error) {
                // Set the error message
                addToast(t('user.errorUnableToSendFollow') + " - " + error.toString(), 'danger', true);
            }
        }

        async function submitCancelFollowUser() {
            try {
                await followers.deleteUserFollowsSpecificUser(authStore.user.id, userProfile.value.id);

                userFollowState.value = null;

                // Set the success message
                addToast(t('user.successFollowRequestCancelled'), 'success', true);
            } catch (error) {
                // Set the error message
                addToast(t('user.errorUnableToSendFollow') + " - " + error.toString(), 'danger', true);
            }
        }

        async function submitUnfollowUser() {
            try {
                await followers.deleteUserFollowsSpecificUser(authStore.user.id, userProfile.value.id);

                userFollowState.value = null;

                // Set the success message
                addToast(t('user.successUserUnfollowed'), 'success', true);
            } catch (error) {
                // Set the error message
                addToast(t('user.errorUnableToUnfollow') + " - " + error.toString(), 'danger', true);
            }
        }

        return {
            isLoading,
            isActivitiesLoading,
            authStore,
            userProfile,
            thisMonthNumberOfActivities,
            followersCountAccepted,
            followingCountAccepted,
            followersAll,
            followingAll,
            thisWeekDistances,
            thisMonthDistances,
            t,
            week,
            formatDateRange,
            setWeek,
            visibleWeeks,
            userWeekActivities,
            userFollowState,
            updateFollowingList,
            updateFollowerList,
            updateFollowerListWithAccepted,
            submitFollowUser,
            submitCancelFollowUser,
            submitUnfollowUser,
        };
    },
};  
</script>