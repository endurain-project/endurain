import { defineStore } from 'pinia';
import { useAuthStore } from '@/stores/authStore';
// Import the services
import { activities } from '@/services/activitiesService';
import { followers } from '@/services/followersService';

export const useUserStore = defineStore('user', {
    state: () => ({
        authStore: useAuthStore(),
        thisWeekDistances: null,
        thisMonthDistances: null,
        thisMonthNumberOfActivities: 0,
        userNumberOfActivities: 0,
        userActivities: [],
        followedUserActivities: [],
        userFollowersCountAll: 0,
        userFollowersAll: [],
        userFollowersCountAccepted: 0,
        //userFollowersAccepted: [],
        userFollowingCountAll: 0,
        userFollowingAll: [],
        userFollowingCountAccepted: 0,
        //userFollowingAccepted: [],
    }),
    actions: {
        async fetchUserStats() {
            try {
                this.thisWeekDistances = await activities.getUserThisWeekStats(this.authStore.user.id);
                this.thisMonthDistances = await activities.getUserThisMonthStats(this.authStore.user.id);
            } catch (error) {
                console.error("Failed to fetch data:", error);
            }
        },
        async fetchUserThisMonthActivitiesNumber(){
            try {
                this.thisMonthNumberOfActivities = await activities.getUserThisMonthActivitiesNumber(this.authStore.user.id);
            } catch (error) {
                console.error("Failed to fetch data:", error);
            }
        },
        async fetchUserActivitiesNumber(){
            try {
                this.userNumberOfActivities = await activities.getUserNumberOfActivities(this.authStore.user.id);
            } catch (error) {
                console.error("Failed to fetch data:", error);
            }
        },
        async fetchUserActivitiesWithPagination(pageNumber, numRecords){
            try {
                const newActivities = await activities.getUserActivitiesWithPagination(this.authStore.user.id, pageNumber, numRecords);

                Array.prototype.push.apply(this.userActivities, newActivities);
            } catch (error) {
                console.error("Failed to fetch data:", error);
            }
        },
        async fetchUserFollowedActivitiesWithPagination(pageNumber, numRecords){
            try {
                this.followedUserActivities = await activities.getUserFollowersActivitiesWithPagination(this.authStore.user.id, pageNumber, numRecords);
            } catch (error) {
                console.error("Failed to fetch data:", error);
            }
        },
        async fetchNewUserActivity(activityId){
            try {
                const newActivity = await activities.getActivityById(activityId);
                this.userActivities.unshift(newActivity);
            } catch (error) {
                console.error("Failed to fetch data:", error);
            }
        },
        async fetchUserFollowersAll(){
            try {
                this.userFollowersAll = await followers.getUserFollowersAll(this.authStore.user.id);
            } catch (error) {
                console.error("Failed to fetch data:", error);
            }
        },
        async fetchUserFollowersCountAll(){
            try {
                this.userFollowersCountAll = await followers.getUserFollowersCountAll(this.authStore.user.id);
            } catch (error) {
                console.error("Failed to fetch data:", error);
            }
        },
        async fetchUserFollowersCountAccepted(){
            try {
                this.userFollowersCountAccepted = await followers.getUserFollowersCountAccepted(this.authStore.user.id);
            } catch (error) {
                console.error("Failed to fetch data:", error);
            }
        },
        async fetchUserFollowingAll(){
            try {
                this.userFollowingAll = await followers.getUserFollowingAll(this.authStore.user.id);
            } catch (error) {
                console.error("Failed to fetch data:", error);
            }
        },
        async fetchUserFollowingCountAll(){
            try {
                this.userFollowingCountAll = await followers.getUserFollowingCountAll(this.authStore.user.id);
            } catch (error) {
                console.error("Failed to fetch data:", error);
            }
        },
        async fetchUserFollowingCountAccepted(){
            try {
                this.userFollowingCountAccepted = await followers.getUserFollowingCountAccepted(this.authStore.user.id);
            } catch (error) {
                console.error("Failed to fetch data:", error);
            }
        },
        // Action to reset the store state
        resetStore() {
            Object.assign(this.$state, getDefaultState());
        }
    }
});