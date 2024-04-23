<template>
    <!-- Error alerts -->
    <ErrorAlertComponent v-if="errorMessage"/>

    <div class="row align-items-center">
        <!-- picture col -->
        <div class="col">
            <div v-if="isLoading">
                <LoadingComponent />
            </div>
            <div class="vstack d-flex justify-content-center" v-else>
                <div class="d-flex justify-content-center">
                    <img :src="userMe.photo_path" alt="User Photo" width="120" height="120" class="rounded-circle" v-if="userMe.photo_path">
                    <img src="/src/assets/avatar/male1.png" alt="Default Male Avatar" width="120" height="120" class="rounded-circle" v-else-if="!userMe.photo_path && userMe.gender == 1">
                    <img src="/src/assets/avatar/female1.png" alt="Default Female Avatar" width="120" height="120" class="rounded-circle" v-else>
                </div>
                <div class="text-center mt-3 mb-3">
                    <h3>
                        <span>{{ userMe.name }}</span>
                    </h3>
                    <span class="fw-lighter" v-if="userMe.city">
                        <font-awesome-icon :icon="['fas', 'location-dot']" />
                        {{ userMe.city }}
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
                    {{ userThisMonthNumberOfActivities }}
                </h1>
                <div class="row align-items-center">
                    <div class="col">
                        {{ userFollowingCountAccepted }}
                        <br>
                        <span class="fw-lighter">
                            {{ $t("user.userFollowing") }}
                        </span>
                    </div>
                    <div class="col">
                        {{ userFollowersCountAccepted }}
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
            <UserDistanceStatsComponent v-else />
        </div>
    </div>

    <!-- navigation -->
    <div v-if="isLoading">
        <LoadingComponent />
    </div>
    <ul class="nav nav-pills mb-3 justify-content-center" id="pills-tab" role="tablist" v-else>
        <li class="nav-item" role="presentation">
            <button class="nav-link active" id="pills-activities-tab" data-bs-toggle="pill"
                data-bs-target="#pills-activities" type="button" role="tab" aria-controls="pills-activities"
                aria-selected="true">
                {{ $t("user.navigationActivities") }}
            </button>
        </li>
        <li class="nav-item" role="presentation">
            <button class="nav-link" id="pills-following-tab" data-bs-toggle="pill"
                data-bs-target="#pills-following" type="button" role="tab" aria-controls="pills-following"
                aria-selected="false">
                {{ $t("user.navigationFollowing") }}
            </button>
        </li>
        <li class="nav-item" role="presentation">
            <button class="nav-link" id="pills-followers-tab" data-bs-toggle="pill"
                data-bs-target="#pills-followers" type="button" role="tab" aria-controls="pills-followers"
                aria-selected="false">
                {{ $t("user.navigationFollowers") }}
            </button>
        </li>
        <li class="nav-item" role="presentation" v-if="userMe.id == loggedUserId">
            <router-link :to="{ name: 'settings', query: { profileSettings: 1 }}" class="btn nav-link">
                <font-awesome-icon :icon="['fas', 'fa-gear']" />
                {{ $t("user.navigationUserSettings") }}
            </router-link>
        </li>
        <li class="nav-item" role="presentation" v-if="userMe.id != loggedUserId && userFollowState == null">
            <a class="btn btn-outline-success h-100 ms-2" href="#" role="button" data-bs-toggle="modal"
                data-bs-target="#followUserModal">
                <font-awesome-icon :icon="['fas', 'fa-user-plus']" />
                {{ $t("user.navigationFollow") }}
            </a>
        </li>
        <li class="nav-item" role="presentation" v-if="userMe.id != loggedUserId && userFollowState != null && !userFollowState.is_accepted">
            <a class="btn btn-outline-secondary h-100 ms-2" href="#" role="button" data-bs-toggle="modal"
                data-bs-target="#cancelFollowUserModal">
                <font-awesome-icon :icon="['fas', 'fa-user-plus']" />
                {{ $t("user.navigationRequestSent") }}
            </a>
        </li>
        <li class="nav-item" role="presentation" v-if="userMe.id != loggedUserId && userFollowState != null && userFollowState.is_accepted">
            <a class="btn btn-outline-danger h-100 ms-2" href="#" role="button" data-bs-toggle="modal"
                data-bs-target="#unfollowUserModal">
                <font-awesome-icon :icon="['fas', 'fa-user-minus']" />
                {{ $t("user.navigationUnfollow") }}
            </a>
        </li>
    </ul>

    <div class="tab-content" id="pills-tabContent">
        <!-- activities tab content -->
        <div class="tab-pane fade show active" id="pills-activities" role="tabpanel" aria-labelledby="pills-activities-tab" tabindex="0">
            <!-- pagination -->
            <nav>
                <ul class="pagination justify-content-center">
                    <li :class="['page-item', { active: week === 0 }]" >
                        <a href="#" class="page-link" @click="setWeek(0, $event)">
                            {{ $t("user.activitiesPaginationWeek0") }}
                        </a>
                    </li>
                    <li v-if="week > 2" class="page-item disabled">
                        <a class="page-link">...</a>
                    </li>
                    <li v-for="i in visibleWeeks" :key="i" :class="['page-item', { active: i === week }]" >
                        <a href="#" class="page-link" @click="setWeek(i, $event)">
                            {{ formatDateRange(i) }}
                        </a>
                    </li>
                    <li v-if="week < 49" class="page-item disabled">
                        <a class="page-link">...</a>
                    </li>
                    <li :class="['page-item', { active: week === 51 }]" >
                        <a href="#" class="page-link" @click="setWeek(51, $event)">
                            {{ $t("user.activitiesPaginationWeek51") }}
                        </a>
                    </li>
                </ul>
            </nav>

            <!-- activities -->
            <div v-if="isActivitiesLoading">
                <LoadingComponent />
            </div>
            <div v-else>
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
        </div>

        <!-- following tab content -->
        <div class="tab-pane fade" id="pills-following" role="tabpanel" aria-labelledby="pills-following-tab" tabindex="0">
            <div v-if="isLoading">
                <LoadingComponent />
            </div>
            <div v-else>
                <div v-if="userFollowersAll && userFollowersAll.length">
                    <ul class="list-group list-group-flush align-items-center">
                        <div class="card mb-3" v-for="follower in userFollowersAll" :key="follower.following_id">
                            <FollowersListComponent :follower="follower"/>
                        </div>
                    </ul>
                </div>
                <!-- Displaying a message or component when there are no following users -->
                <NoItemsFoundComponent v-else />
            </div>
        </div>
    </div>

    <!-- back button -->
    <div>
        <br>
        <button @click="goBack" type="button" class="w-100 btn btn-primary d-lg-none">{{ $t("generalItens.buttonBack") }}</button>
    </div>
</template>

<script>
import { ref, onMounted, computed, watchEffect, watch } from 'vue';
import { useRoute } from 'vue-router';
import { useI18n } from 'vue-i18n';
import { useUserStore } from '@/stores/user';
import { activities } from '@/services/activities';
import { followers } from '@/services/followers';
// Importing the stores
import { useErrorAlertStore } from '@/stores/Alerts/errorAlert';
// Importing the components
import UserDistanceStatsComponent from '@/components/Activities/UserDistanceStatsComponent.vue';
import LoadingComponent from '@/components/LoadingComponent.vue';
import NoItemsFoundComponent from '@/components/NoItemsFoundComponents.vue';
import ActivitySummaryComponent from '@/components/Activities/ActivitySummaryComponent.vue';
import ActivityMapComponent from '@/components/Activities/ActivityMapComponent.vue';
import ErrorAlertComponent from '@/components/Alerts/ErrorAlertComponent.vue';
import FollowersListComponent from '@/components/Followers/FollowersListComponent.vue';

export default {
    components: {
        UserDistanceStatsComponent,
        NoItemsFoundComponent,
        LoadingComponent,
        ActivitySummaryComponent,
        ActivityMapComponent,
        ErrorAlertComponent,
        FollowersListComponent,
    },
    setup () {
        const idFromParam = computed(() => route.params.id);
        const userStore = useUserStore();
        const errorAlertStore = useErrorAlertStore();
        const route = useRoute();
        const loggedUserId = JSON.parse(localStorage.getItem('userMe')).id;
        const userMe = computed(() => userStore.userMe);
        const userThisMonthNumberOfActivities = computed(() => userStore.thisMonthNumberOfActivities);
        const userFollowersCountAccepted = computed(() => userStore.userFollowingCountAccepted);
        const userFollowingCountAccepted = computed(() => userStore.userFollowersCountAccepted);
        const userFollowersAll = computed(() => userStore.userFollowingAll);
        const userFollowingAll = computed(() => userStore.userFollowersAll);
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
        const errorMessage = ref('');
        const userFollowState = ref(null);

        onMounted(async () => {
            try {
                // Fetch the user stats
                await userStore.fetchUserMe(route.params.id);
                await userStore.fetchUserStats();
                await userStore.fetchUserThisMonthActivitiesNumber();
                await userStore.fetchUserFollowersCountAccepted();
                await userStore.fetchUserFollowingCountAccepted();
                await userStore.fetchUserFollowersAll();
                await userStore.fetchUserFollowingAll();
                userWeekActivities.value = activities.getUserWeekActivities(userMe.value.id, week.value);
                if (userMe.value.id != loggedUserId) {
                    userFollowState.value = await followers.getUserFollowState(loggedUserId, userMe.value.id);
                }
                console.log(userFollowersAll.value, userFollowingAll.value);
            } catch (error) {
                // Set the error message
                errorMessage.value = t('generalItens.errorFetchingInfo') + " - " + error.toString();
                errorAlertStore.setAlertMessage(errorMessage.value);
            }

            isLoading.value = false;
            isActivitiesLoading.value = false;
        });

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
                userWeekActivities.value = await activities.getUserWeekActivities(userMe.value.id, week.value);
            } catch (error) {
                // Set the error message
                errorMessage.value = t('generalItens.errorFetchingInfo') + " - " + error.toString();
                errorAlertStore.setAlertMessage(errorMessage.value);
            } finally {
                isActivitiesLoading.value = false;
            }
        }

        function goBack() {
            route.go(-1);
        }

        return {
            idFromParam,
            isLoading,
            isActivitiesLoading,
            loggedUserId,
            userMe,
            userThisMonthNumberOfActivities,
            userFollowersCountAccepted,
            userFollowingCountAccepted, 
            goBack,
            t,
            week,
            formatDateRange,
            setWeek,
            visibleWeeks,
            userWeekActivities,
            errorMessage,
            userFollowState,
            userFollowersAll,
            userFollowingAll
        };
    },
};  
</script>