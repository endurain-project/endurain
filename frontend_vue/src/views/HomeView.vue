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
          <UserDistanceStatsComponent />
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
          <input type="radio" class="btn-check" name="btnradio" id="btnRadioUserActivities" autocomplete="off" value="userActivities" v-model="selectedActivity">
          <label class="btn btn-outline-primary w-100" for="btnRadioUserActivities">{{ $t("home.radioUserActivities") }}</label>
          <!-- user followers activities -->
          <input type="radio" class="btn-check" name="btnradio" id="btnRadioFollowersActivities" autocomplete="off" value="followersActivities" v-model="selectedActivity">
          <label class="btn btn-outline-primary w-100" for="btnRadioFollowersActivities">{{ $t("home.radioFollowerActivities") }}</label>
        </div>

        <!-- user activities -->
        <div id="userActivitiesDiv" v-show="selectedActivity === 'userActivities'">
          <NoItemsFoundComponent v-if="userActivities"/>
        </div>

        <!-- user followers activities -->
        <div id="followersActivitiesDiv" v-show="selectedActivity === 'followersActivities'">
          <NoItemsFoundComponent v-if="followedUserActivities"/>
        </div>
      </div>
    </div>
  </div>
</template>

<script>
import { ref, onMounted } from 'vue';
import { useUserStore } from '@/stores/user';
import UserDistanceStatsComponent from '@/components/UserDistanceStatsComponent.vue';
import NoItemsFoundComponent from '@/components/NoItemsFoundComponents.vue';

export default {
  components: {
    UserDistanceStatsComponent,
    NoItemsFoundComponent,
  },
  setup() {
    const userStore = useUserStore();
    const selectedActivity = ref('userActivities');

    onMounted(() => {
      userStore.fetchUserStats();
      userStore.fetchUserActivitiesWithPagination(1, 5);
    });

    return {
      selectedActivity,
      userMe: userStore.userMe,
      thisWeekDistances: userStore.thisWeekDistances,
      thisMonthDistances: userStore.thisMonthDistances,
      userActivities: userStore.userActivities,
      followedUserActivities: userStore.followedUserActivities,
    };
  },
};
</script>