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
      </div>
      <!-- activities zone -->
      <div class="col">

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
import { useUserStore } from '@/stores/user';
import UserDistanceStatsComponent from '@/components/Activities/UserDistanceStatsComponent.vue';
import NoItemsFoundComponent from '@/components/NoItemsFoundComponents.vue';
import ActivitySummaryComponent from '@/components/Activities/ActivitySummaryComponent.vue';
import LoadingComponent from '@/components/LoadingComponent.vue';

export default {
  components: {
    UserDistanceStatsComponent,
    NoItemsFoundComponent,
    ActivitySummaryComponent,
    LoadingComponent,
  },
  setup() {
    const userStore = useUserStore();
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

    const fetchMoreActivities = async () => {
      if (isLoading.value || !userHasMoreActivities.value) return;

      pageNumberUserActivities.value++;
      try {
        // Assuming your store method can handle appending to the existing activities
        await userStore.fetchUserActivitiesWithPagination(pageNumberUserActivities.value, numRecords);
        // Implement logic to set hasMoreActivities to false if no more activities are returned
        if ((pageNumberUserActivities.value * numRecords) >= userNumberOfActivities.value) {
          userHasMoreActivities.value = false;
        }
      } catch (error) {
        console.error("Error fetching more activities", error);
      }
    };

    const handleScroll = () => {
      const bottomOfWindow = document.documentElement.scrollTop + window.innerHeight === document.documentElement.offsetHeight;

      if (bottomOfWindow) {
        fetchMoreActivities();
      }
    };

    onMounted(async () => {
      window.addEventListener('scroll', handleScroll);

      await userStore.fetchUserStats();
      await userStore.fetchUserActivitiesNumber();
      await userStore.fetchUserActivitiesWithPagination(1, numRecords);
      await userStore.fetchUserFollowedActivitiesWithPagination(1, numRecords);

      isLoading.value = false;
    });

    onUnmounted(() => {
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
    };
  },
};
</script>