import { defineStore } from 'pinia';
import { activities } from '@/services/activities';

export const useUserStore = defineStore('user', {
    state: () => ({
        userMe: JSON.parse(localStorage.getItem('userMe')) || {},
        thisWeekDistances: null,
        thisMonthDistances: null,
        userNumberOfActivities: 0,
        userActivities: [],
        followedUserActivities: [],
    }),
    actions: {
        async fetchUserStats() {
            try {
                this.thisWeekDistances = await activities.getUserThisWeekStats(this.userMe.id);
                this.thisMonthDistances = await activities.getUserThisMonthStats(this.userMe.id);
            } catch (error) {
                console.error("Failed to fetch data:", error);
            }
        },
        async fetchUserActivitiesNumber(){
            try {
                this.userNumberOfActivities = await activities.getUserNumberOfActivities(this.userMe.id);
            } catch (error) {
                console.error("Failed to fetch data:", error);
            }
        },
        async fetchUserActivitiesWithPagination(pageNumber, numRecords){
            try {
                const newActivities = await activities.getUserActivitiesWithPagination(this.userMe.id, pageNumber, numRecords);

                Array.prototype.push.apply(this.userActivities, newActivities);
            } catch (error) {
                console.error("Failed to fetch data:", error);
            }
        },
        async fetchUserFollowedActivitiesWithPagination(pageNumber, numRecords){
            try {
                this.followedUserActivities = await activities.getUserFollowersActivitiesWithPagination(this.userMe.id, pageNumber, numRecords);
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
    }
});