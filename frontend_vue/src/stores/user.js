import { defineStore } from 'pinia';
import { activities } from '@/services/activities';

export const useUserStore = defineStore('user', {
    state: () => ({
        userMe: JSON.parse(localStorage.getItem('userMe')) || {},
        thisWeekDistances: null,
        thisMonthDistances: null,
        userActivities: null,
        followedUserActivities: null,
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
        async fetchUserActivitiesWithPagination(pageNumber, numRecords){
            try {
                this.userActivities = await activities.getUserActivitiesWithPagination(this.userMe.id, pageNumber, numRecords);
                this.followedUserActivities = await activities.getUserFollowersActivitiesWithPagination(this.userMe.id, pageNumber, numRecords);
            } catch (error) {
                console.error("Failed to fetch data:", error);
            }
        }
    }
});