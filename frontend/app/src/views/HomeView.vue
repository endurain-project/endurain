<template>
	<div class="row">
		<!-- sidebar zone -->
		<div class="col-lg-3 col-md-12">
			<div class="sticky-sidebar">
				<div class="d-none d-lg-block d-flex mb-3 rounded p-3 bg-body-tertiary shadow-sm">
					<!-- user name and photo zone -->
					<div v-if="isLoading">
						<LoadingComponent />
					</div>
					<div v-else>
						<div class="justify-content-center d-flex" v-if="authStore.user">
							<UserAvatarComponent :user="authStore.user" :width=120 :height=120 />
						</div>
						<div class="text-center mt-3 fw-bold" v-if="authStore.user.id">
							<router-link :to="{ name: 'user', params: { id: authStore.user.id }}" class="link-body-emphasis link-underline-opacity-0 link-underline-opacity-100-hover">
								{{ authStore.user.name}}
							</router-link>
						</div>
					</div>
					<!-- user stats zone -->
					<div v-if="isLoading">
						<LoadingComponent />
					</div>
					<UserDistanceStatsComponent :thisWeekDistances="thisWeekDistances" :thisMonthDistances="thisMonthDistances" v-else />
				</div>

				<!-- add activity and refresh buttons -->
				<div class="row mb-3">
					<div class="col">
						<a class="w-100 btn btn-primary shadow-sm" href="#" role="button" data-bs-toggle="modal" data-bs-target="#addActivityModal">
							{{ $t("homeView.buttonAddActivity") }}
						</a>
					</div>
					<div class="col-4" v-if="authStore.user.is_strava_linked == 1 || authStore.user.is_garminconnect_linked == 1">
						<a class="w-100 btn btn-primary shadow-sm" href="#" role="button" @click="refreshActivities">
							<font-awesome-icon :icon="['fas', 'arrows-rotate']" />
						</a>
					</div>
				</div>
			</div>

			<!-- Modal add actvity -->
			<div class="modal fade" id="addActivityModal" tabindex="-1" aria-labelledby="addActivityModalLabel" aria-hidden="true">
				<div class="modal-dialog">
					<div class="modal-content">
						<div class="modal-header">
							<h1 class="modal-title fs-5" id="addActivityModalLabel">
								{{ $t("homeView.buttonAddActivity") }}
							</h1>
							<!--<button type="button" class="btn-close" data-bs-dismiss="modal" aria-label="Close"></button>-->
						</div>
						<form @submit.prevent="submitUploadFileForm">
							<div class="modal-body">
								<!-- date fields -->
								<label for="activityGpxFileAdd"><b>* {{ $t("homeView.fieldLabelUploadGPXFile") }}</b></label>
								<input class="form-control mt-1 mb-1" type="file" name="activityGpxFileAdd" accept=".gpx,.fit" required>
								<p>* {{ $t("generalItems.requiredField") }}</p>
							</div>
							<div class="modal-footer">
								<button type="button" class="btn btn-secondary" data-bs-dismiss="modal">
								{{ $t("generalItems.buttonClose") }}
								</button>
								<button type="submit" class="btn btn-success" data-bs-dismiss="modal">
								{{ $t("homeView.buttonAddActivity") }}
								</button>
							</div>
						</form>
					</div>
				</div>
			</div>
		</div>
		<!-- activities zone -->
		<div class="col">

		<!-- radio button -->
		<!-- <div class="btn-group mb-3 d-flex" role="group"  aria-label="Activities radio toggle button group"> -->
			<!-- user activities -->
			<!-- <input type="radio" class="btn-check" name="btnradio" id="btnRadioUserActivities" autocomplete="off" value="userActivities" v-model="selectedActivityView">
			<label class="btn btn-outline-primary w-100" for="btnRadioUserActivities">{{ $t("homeView.radioUserActivities") }}</label> -->
			<!-- user followers activities -->
			<!-- <input type="radio" class="btn-check" name="btnradio" id="btnRadioFollowersActivities" autocomplete="off" value="followersActivities" v-model="selectedActivityView">
			<label class="btn btn-outline-primary w-100" for="btnRadioFollowersActivities">{{ $t("homeView.radioFollowerActivities") }}</label>
		</div> -->

		<!-- user activities -->
		<div id="userActivitiesDiv" v-show="selectedActivityView === 'userActivities'">
			<div v-if="isLoading">
				<LoadingComponent />
			</div>
			<div v-else>
				<!-- Checking if userActivities is loaded and has length -->
				<div v-if="userActivities && userActivities.length">
					<!-- Iterating over userActivities to display them -->
					<div class="card mb-3 bg-body-tertiary border-0 shadow-sm" v-for="activity in userActivities" :key="activity.id">
						<div class="card-body">
							<ActivitySummaryComponent :activity="activity" :source="'home'" :units="authStore.user.units"/>
						</div>
						<ActivityMapComponent class="mx-3 mb-3" :activity="activity" :source="'home'"/>
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

				</div>
				<NoItemsFoundComponent v-else />
				</div>
			</div>
		</div>
	</div>
</template>

<style scoped>
.sticky-sidebar {
    position: sticky;
    top: 20px; /* Adjust based on your layout */
    z-index: 1000;
}
</style>

<script>
import { ref, onMounted, onUnmounted, watchEffect, computed } from "vue";
import { useI18n } from "vue-i18n";
import { useRoute } from "vue-router";
// Import the stores
import { useAuthStore } from "@/stores/authStore";
// Import the services
import { activities } from "@/services/activitiesService";
import { followers } from "@/services/followersService";
// Import Notivue push
import { push } from "notivue";
// Importing the components
import UserDistanceStatsComponent from "@/components/Activities/UserDistanceStatsComponent.vue";
import NoItemsFoundComponent from "@/components/GeneralComponents/NoItemsFoundComponents.vue";
import ActivitySummaryComponent from "@/components/Activities/ActivitySummaryComponent.vue";
import ActivityMapComponent from "@/components/Activities/ActivityMapComponent.vue";
import LoadingComponent from "@/components/GeneralComponents/LoadingComponent.vue";
import UserAvatarComponent from "@/components/Users/UserAvatarComponent.vue";

//import { Modal } from 'bootstrap';

export default {
	components: {
		UserDistanceStatsComponent,
		NoItemsFoundComponent,
		ActivitySummaryComponent,
		ActivityMapComponent,
		LoadingComponent,
		UserAvatarComponent,
	},
	setup() {
		const route = useRoute();
		const authStore = useAuthStore();
		const selectedActivityView = ref("userActivities");
		const isLoading = ref(true);
		const thisWeekDistances = ref([]);
		const thisMonthDistances = ref([]);
		const userNumberOfActivities = ref(0);
		const userActivities = ref([]);
		const followedUserActivities = ref([]);
		const pageNumberUserActivities = ref(1);
		const numRecords = 5;
		const userHasMoreActivities = ref(true);
		const { t } = useI18n();

		async function fetchUserStars() {
			try {
				thisWeekDistances.value = await activities.getUserThisWeekStats(
					authStore.user.id,
				);
				thisMonthDistances.value = await activities.getUserThisMonthStats(
					authStore.user.id,
				);
			} catch (error) {
				// Set the error message
				push.error(`${t("homeView.errorFetchingUserStats")} - ${error}`);
			}
		}

		async function fetchMoreActivities() {
			// If the component is already loading or there are no more activities, return
			if (isLoading.value || !userHasMoreActivities.value) return;

			// Add 1 to the page number
			pageNumberUserActivities.value++;
			try {
				// Fetch the activities
				const newActivities = await activities.getUserActivitiesWithPagination(
					authStore.user.id,
					pageNumberUserActivities.value,
					numRecords,
				);
				Array.prototype.push.apply(userActivities.value, newActivities);

				// If the number of activities is greater than the page number times the number of records, there are no more activities
				if (
					pageNumberUserActivities.value * numRecords >=
					userNumberOfActivities.value
				) {
					userHasMoreActivities.value = false;
				}
			} catch (error) {
				// Set the error message
				push.error(`${t("homeView.errorFetchingUserActivities")} - ${error}`);
			}
		}
		
		const handleScroll = () => {
			// If the component is already loading or there are no more activities, return
			if (isLoading.value || !userHasMoreActivities.value) return;

			const bottomOfWindow =
				window.innerHeight + window.scrollY >= document.documentElement.scrollHeight - 1;

			// If the user has reached the bottom of the page, fetch more activities
			if (bottomOfWindow) {
				fetchMoreActivities();
			}
		};

		const submitUploadFileForm = async () => {
			// Set the loading message
			const notification = push.promise(t("homeView.processingActivity"));

			// Get the file input
			const fileInput = document.querySelector('input[type="file"]');

			// If there is a file, create the form data and upload the file
			if (fileInput.files[0]) {
				// Create the form data
				const formData = new FormData();
				formData.append("file", fileInput.files[0]);
				try {
					// Upload the file
					const createdActivities =
						await activities.uploadActivityFile(formData);
					// Fetch the new user activity
					if (!userActivities.value) {
						userActivities.value = [];
					}
					for (const createdActivity of createdActivities) {
						userActivities.value.unshift(createdActivity);
					}

					// Set the success message
					notification.resolve(t("homeView.successActivityAdded"));

					// Clear the file input
					fileInput.value = "";

					// Fetch the user stats
					fetchUserStars();

					// Fetch the user activities and user activities number
					userNumberOfActivities.value++;
				} catch (error) {
					// Set the error message
					notification.reject(`${error}`);
				}
			}
		};

		async function refreshActivities() {
			// Set the loading message
			const notification = push.promise(t("homeView.refreshingActivities"));

			try {
				console.log("Refreshing activities");
				// Get the user activities
				const newActivities = await activities.getActivityRefresh();

				// If userActivities is not defined, do it
				if (!userActivities.value) {
					userActivities.value = [];
				}

				// Iterate over the new activities and add them to the user activities
				if (newActivities) {
					for (const newActivity of newActivities) {
						userActivities.value.unshift(newActivity);
					}
				}

				// Set the success message
				notification.resolve(t("homeView.successActivitiesRefreshed"));

				// Fetch the user stats
				fetchUserStars();
				
				// Set the user number of activities
				console.log(userNumberOfActivities.value);
				userNumberOfActivities.value += newActivities.length; 
				console.log(userNumberOfActivities.value);
			} catch (error) {
				// Set the error message
				notification.reject(`${error}`);
			}
		}

		onMounted(async () => {
			if (route.query.activityFound === "false") {
				// Set the activityFound value to false and show the error alert.
				push.error(t("homeView.errorActivityNotFound"));
			}

			if (route.query.activityDeleted === "true") {
				userActivities.value = userActivities.value.filter(
					(activity) => activity.id !== Number(route.query.activityId),
				);
				// Set the activityDeleted value to true and show the success alert.
				push.success(t("homeView.successActivityDeleted"));
			}

			// Add the scroll event listener
			window.addEventListener("scroll", handleScroll);

			try {
				// Fetch the user stats
				fetchUserStars();

				// Fetch the user activities and user activities number
				userNumberOfActivities.value =
					await activities.getUserNumberOfActivities(authStore.user.id);
				userActivities.value = await activities.getUserActivitiesWithPagination(
					authStore.user.id,
					pageNumberUserActivities.value,
					numRecords,
				);
				//followedUserActivities.value = await activities.getUserFollowersActivitiesWithPagination(authStore.user.id, pageNumberUserActivities, numRecords);

				// If the number of activities is greater than the page number times the number of records, there are no more activities
				if (
					pageNumberUserActivities.value * numRecords >=
					userNumberOfActivities.value
				) {
					userHasMoreActivities.value = false;
				}
			} catch (error) {
				// Set the error message
				push.error(`${t("homeView.errorFetchingUserActivities")} - ${error}`);
			}

			isLoading.value = false;
		});

		onUnmounted(() => {
			// Remove the scroll event listener
			window.removeEventListener("scroll", handleScroll);
		});

		return {
			authStore,
			selectedActivityView,
			isLoading,
			thisWeekDistances,
			thisMonthDistances,
			userActivities,
			followedUserActivities,
			submitUploadFileForm,
			t,
			refreshActivities
		};
	},
};
</script>