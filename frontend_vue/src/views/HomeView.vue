<template>
  <div class="container mt-4">
    <div class="row row-gap-3">
      <!-- sidebar zone -->
      <div class="col-lg-3 col-md-12">
        <div class="d-none d-lg-block mt-3 mb-3 d-flex justify-content-center">
          <!-- user name and photo zone -->
          <div class="justify-content-center d-flex">
            <img :src="userMe.photo_path" alt="User Photo" width="120" height="120" class="rounded-circle" v-if="userMe.photo_path">
            <img src="/src/assets/avatar/male1.png" alt="Default Male Avatar" width="120" height="120" class="rounded-circle" v-else-if="!userMe.photo_path && userMe.gender == 1">
            <img src="/src/assets/avatar/female1.png" alt="Default Female Avatar" width="120" height="120" class="rounded-circle" v-else>
          </div>
          <div class="text-center mt-3 mb-3 fw-bold">
            <a href="">
              <span>{{ userMe.name }}</span>
            </a>
          </div>
          <!-- user stats zone -->
          <div v-if="isLoading">
            <LoadingComponent />
          </div>
          <UserDistanceStatsComponent v-else />
        </div>
        <a class="w-100 btn btn-primary" href="#" role="button" data-bs-toggle="modal" data-bs-target="#addActivityModal">
          {{ $t("home.buttonAddActivity") }}
        </a>

        <!-- Modal add actvity -->
        <div class="modal fade" id="addActivityModal" tabindex="-1" aria-labelledby="addActivityModalLabel" aria-hidden="true">
          <div class="modal-dialog">
            <div class="modal-content">
              <div class="modal-header">
                <h1 class="modal-title fs-5" id="addActivityModalLabel">
                  {{ $t("home.buttonAddActivity") }}
                </h1>
                <!--<button type="button" class="btn-close" data-bs-dismiss="modal" aria-label="Close"></button>-->
              </div>
              <form @submit.prevent="submitUploadFileForm">
                <div class="modal-body">
                  <!-- date fields -->
                  <label for="activityGpxFileAdd"><b>* {{ $t("home.fieldLabelUploadGPXFile") }}</b></label>
                  <input class="form-control mt-1 mb-1" type="file" name="activityGpxFileAdd" accept=".gpx" required>
                  <p>* {{ $t("generalItens.requiredField") }}</p>
                </div>
                <div class="modal-footer">
                  <button type="button" class="btn btn-secondary" data-bs-dismiss="modal">
                    {{ $t("generalItens.buttonClose") }}
                  </button>
                  <button type="submit" class="btn btn-success">
                    {{ $t("home.buttonAddActivity") }}
                  </button>
                </div>
              </form>
            </div>
          </div>
        </div>
      </div>
      <!-- activities zone -->
      <div class="col">
        <!-- Error alerts -->
        <ErrorAlertComponent v-if="errorMessage"/>

        <!-- Success banners -->
        <SuccessAlertComponent v-if="successMessage"/>

        <!-- radio button -->
        <div class="btn-group mb-3 d-flex" role="group"  aria-label="Activities radio toggle button group">
          <!-- user activities -->
          <input type="radio" class="btn-check" name="btnradio" id="btnRadioUserActivities" autocomplete="off" value="userActivities" v-model="selectedActivityView">
          <label class="btn btn-outline-primary w-100" for="btnRadioUserActivities">{{ $t("home.radioUserActivities") }}</label>
          <!-- user followers activities -->
          <input type="radio" class="btn-check" name="btnradio" id="btnRadioFollowersActivities" autocomplete="off" value="followersActivities" v-model="selectedActivityView">
          <label class="btn btn-outline-primary w-100" for="btnRadioFollowersActivities">{{ $t("home.radioFollowerActivities") }}</label>
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
              <ActivitySummaryComponent v-for="activity in userActivities" :key="activity.id" :activity="activity" />
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
  </div>
</template>

<script>
import { ref, onMounted, onUnmounted, watchEffect, computed } from 'vue';
import { useI18n } from 'vue-i18n';
import { useUserStore } from '@/stores/user';
import { activities } from '@/services/activities';
// Importing the stores
import { useSuccessAlertStore } from '@/stores/Alerts/successAlert';
import { useErrorAlertStore } from '@/stores/Alerts/errorAlert';
// Importing the components
import UserDistanceStatsComponent from '@/components/Activities/UserDistanceStatsComponent.vue';
import NoItemsFoundComponent from '@/components/NoItemsFoundComponents.vue';
import ActivitySummaryComponent from '@/components/Activities/ActivitySummaryComponent.vue';
import LoadingComponent from '@/components/LoadingComponent.vue';
import ErrorAlertComponent from '@/components/Alerts/ErrorAlertComponent.vue';
import SuccessAlertComponent from '@/components/Alerts/SuccessAlertComponent.vue';

//import { Modal } from 'bootstrap';

export default {
  components: {
    UserDistanceStatsComponent,
    NoItemsFoundComponent,
    ActivitySummaryComponent,
    LoadingComponent,
    ErrorAlertComponent,
    SuccessAlertComponent,
  },
  setup() {
    const userStore = useUserStore();
    const successAlertStore = useSuccessAlertStore();
    const errorAlertStore = useErrorAlertStore();
    const selectedActivityView = ref('userActivities');
    const isLoading = ref(true);
    const userMe = computed(() => userStore.userMe);
    const thisWeekDistances = computed(() => userStore.thisWeekDistances);
    const thisMonthDistances = computed(() => userStore.thisMonthDistances);
    const userActivities = computed(() => userStore.userActivities);
    const followedUserActivities = computed(() => userStore.followedUserActivities);
    const pageNumberUserActivities = ref(1);
    const numRecords = 5;
    const userNumberOfActivities = computed(() => userStore.userNumberOfActivities);
    const userHasMoreActivities = ref(true);
    const { t } = useI18n();
    const successMessage = ref('');
    const errorMessage = ref('');

    async function fetchMoreActivities() {
      // If the component is already loading or there are no more activities, return
      if (isLoading.value || !userHasMoreActivities.value) return;

      // Add 1 to the page number
      pageNumberUserActivities.value++;
      try {
        // Fetch the activities
        await userStore.fetchUserActivitiesWithPagination(pageNumberUserActivities.value, numRecords);
        // If the number of activities is greater than the page number times the number of records, there are no more activities
        if ((pageNumberUserActivities.value * numRecords) >= userNumberOfActivities.value) {
          userHasMoreActivities.value = false;
        }
      } catch (error) {
        // Set the error message
        errorMessage.value = t('generalItens.errorFetchingInfo') + " - " + error.toString();
        errorAlertStore.setAlertMessage(errorMessage.value);
      }
    }

    const handleScroll = () => {
      // If the component is already loading or there are no more activities, return
      const bottomOfWindow = document.documentElement.scrollTop + window.innerHeight === document.documentElement.offsetHeight;

      // If the user has reached the bottom of the page, fetch more activities
      if (bottomOfWindow) {
        fetchMoreActivities();
      }
    };

    const submitUploadFileForm = async () => {
      // Get the file input
      const fileInput = document.querySelector('input[type="file"]');
      
      // If there is a file, create the form data and upload the file
      if (fileInput.files[0]) {
        // Create the form data
        const formData = new FormData();
        formData.append('file', fileInput.files[0]);
        try {
          // Upload the file
          const createdActivity = await activities.uploadActivityFile(formData);
          // Fetch the new user activity
          await userStore.fetchNewUserActivity(createdActivity);
          // Set the success message
          successMessage.value = t('home.successActivityAdded');
          successAlertStore.setAlertMessage(successMessage.value);
          successAlertStore.setClosableState(true);

          // Clear the file input
          fileInput.value = '';

          /* const modalElement = document.getElementById('addActivityModal');
          const modalInstance = Modal.getInstance(modalElement);
          if (modalInstance) {
            modalInstance.hide();
          } */
        }catch (error) {
          // Set the error message
          errorMessage.value = t('generalItens.errorFetchingInfo') + " - " + error.toString();
          errorAlertStore.setAlertMessage(errorMessage.value);
        }
      }
    };

    onMounted(async () => {
      // Add the scroll event listener
      window.addEventListener('scroll', handleScroll);

      try {
        // Fetch the user stats
        await userStore.fetchUserStats();
        // Fetch the user activities and user activities number
        await userStore.fetchUserActivitiesNumber();
        await userStore.fetchUserActivitiesWithPagination(1, numRecords);
        await userStore.fetchUserFollowedActivitiesWithPagination(1, numRecords);

        // If the number of activities is greater than the page number times the number of records, there are no more activities
        if ((pageNumberUserActivities.value * numRecords) >= userNumberOfActivities.value) {
          userHasMoreActivities.value = false;
        }
      } catch (error) {
        // Set the error message
        errorMessage.value = t('generalItens.errorFetchingInfo') + " - " + error.toString();
        errorAlertStore.setAlertMessage(errorMessage.value);
      }

      isLoading.value = false;
    });

    onUnmounted(() => {
      // Remove the scroll event listener
      window.removeEventListener('scroll', handleScroll);
    });

    watchEffect(() => {
      //console.log("Entered watchEffect");
    });

    return {
      selectedActivityView,
      isLoading,
      userMe,
      thisWeekDistances,
      thisMonthDistances,
      userActivities,
      followedUserActivities,
      errorMessage,
      successMessage,
      submitUploadFileForm,
      t,
    };
  },
};
</script>