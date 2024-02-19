import { defineStore } from 'pinia';
import { activities } from '@/services/activities';

export const useUserStore = defineStore('user', {
    state: () => ({
        userMe: JSON.parse(localStorage.getItem('userMe')) || {},
        thisWeekDistances: null,
        thisMonthDistances: null,
        userNumberOfActivities: null,
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
                this.userActivities += await activities.getUserActivitiesWithPagination(this.userMe.id, pageNumber, numRecords);
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
        }
    }
});