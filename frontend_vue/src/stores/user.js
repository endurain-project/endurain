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
        /**
         * Fetches the user's statistics for this week and this month.
         * @returns {Promise<void>} A promise that resolves when the data is fetched successfully.
         */
        async fetchUserStats() {
            try {
                this.thisWeekDistances = await activities.getUserThisWeekStats(this.userMe.id);
                this.thisMonthDistances = await activities.getUserThisMonthStats(this.userMe.id);
            } catch (error) {
                console.error("Failed to fetch data:", error);
            }
        },
        /**
         * Fetches the number of activities for the user.
         * @returns {Promise<void>} A promise that resolves when the number of activities is fetched.
         */
        async fetchUserActivitiesNumber(){
            try {
                this.userNumberOfActivities = await activities.getUserNumberOfActivities(this.userMe.id);
            } catch (error) {
                console.error("Failed to fetch data:", error);
            }
        },
        /**
         * Fetches user activities with pagination.
         * @param {number} pageNumber - The page number to fetch.
         * @param {number} numRecords - The number of records per page.
         * @returns {Promise<void>} - A promise that resolves when the user activities are fetched.
         */
        async fetchUserActivitiesWithPagination(pageNumber, numRecords){
            try {
                const newActivities = await activities.getUserActivitiesWithPagination(this.userMe.id, pageNumber, numRecords);

                Array.prototype.push.apply(this.userActivities, newActivities);
            } catch (error) {
                console.error("Failed to fetch data:", error);
            }
        },
        /**
         * Fetches the user's followed activities with pagination.
         * 
         * @param {number} pageNumber - The page number to fetch.
         * @param {number} numRecords - The number of records to fetch per page.
         * @returns {Promise<void>} - A promise that resolves when the data is fetched successfully.
         */
        async fetchUserFollowedActivitiesWithPagination(pageNumber, numRecords){
            try {
                this.followedUserActivities = await activities.getUserFollowersActivitiesWithPagination(this.userMe.id, pageNumber, numRecords);
            } catch (error) {
                console.error("Failed to fetch data:", error);
            }
        },
        /**
         * Fetches new user activity by activity ID and adds it to the beginning of the user activities array.
         * @param {string} activityId - The ID of the activity to fetch.
         * @returns {Promise<void>} - A promise that resolves when the new activity is fetched and added successfully, or rejects with an error if the fetch fails.
         */
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