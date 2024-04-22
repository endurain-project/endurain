import { defineStore } from 'pinia';
import { activities } from '@/services/activities';
import { followers } from '@/services/followers';

export const useUserStore = defineStore('user', {
    state: () => ({
        userMe: JSON.parse(localStorage.getItem('userMe')) || {},
        thisWeekDistances: null,
        thisMonthDistances: null,
        thisMonthNumberOfActivities: 0,
        userNumberOfActivities: 0,
        userActivities: [],
        followedUserActivities: [],
        userFollowersAll: 0,
        userFollowersAccepted: 0,
        userFollowingAll: 0,
        userFollowingAccepted: 0,
    }),
    actions: {
        /**
         * Fetches the user's statistics for this week and this month.
         * @async
         * @function fetchUserStats
         * @memberof module:stores/user
         * @throws {Error} If there is an error fetching the data.
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
         * Fetches the number of activities for the current user in the current month.
         * @async
         * @function fetchUserThisMonthActivitiesNumber
         * @memberof module:stores/user
         * @throws {Error} If there is an error fetching the data.
         * @returns {Promise<void>} A promise that resolves when the data is fetched successfully.
         */
        async fetchUserThisMonthActivitiesNumber(){
            try {
                this.thisMonthNumberOfActivities = await activities.getUserThisMonthActivitiesNumber(this.userMe.id);
            } catch (error) {
                console.error("Failed to fetch data:", error);
            }
        },
        /**
         * Fetches the number of activities for the user.
         * @async
         * @function fetchUserActivitiesNumber
         * @memberof module:stores/user
         * @throws {Error} If there is an error fetching the data.
         * @returns {Promise<void>} A promise that resolves when the data is fetched successfully.
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
         * @async
         * @function fetchUserActivitiesWithPagination
         * @memberof module:stores/user
         * @throws {Error} If there is an error fetching the data.
         * @param {number} pageNumber - The page number to fetch.
         * @param {number} numRecords - The number of records to fetch per page.
         * @returns {Promise<void>} - A promise that resolves when the user activities are fetched successfully.
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
         * @async
         * @function fetchUserFollowedActivitiesWithPagination
         * @memberof module:stores/user
         * @throws {Error} If there is an error fetching the data.
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
         * @async
         * @function fetchNewUserActivity
         * @memberof module:stores/user
         * @throws {Error} If there is an error fetching the data.
         * @param {string} activityId - The ID of the activity to fetch.
         * @returns {Promise<void>} - A promise that resolves when the new activity is fetched and added successfully.
         */
        async fetchNewUserActivity(activityId){
            try {
                const newActivity = await activities.getActivityById(activityId);
                this.userActivities.unshift(newActivity);
            } catch (error) {
                console.error("Failed to fetch data:", error);
            }
        },
        /**
         * Fetches the count of followers for the current user.
         * @async
         * @function fetchUserFollowersCountAll
         * @memberof module:stores/user
         * @throws {Error} If there is an error while fetching the data.
         * @returns {Promise<void>} - A promise that resolves when the new activity is fetched and added successfully.
         */
        async fetchUserFollowersCountAll(){
            try {
                this.userFollowersAll = await followers.getUserFollowersCountAll(this.userMe.id);
            } catch (error) {
                console.error("Failed to fetch data:", error);
            }
        },
        /**
         * Fetches the count of accepted followers for the current user.
         * @async
         * @function fetchUserFollowersCountAccepted
         * @memberof module:stores/user
         * @throws {Error} If there is an error while fetching the data.
         * @returns {Promise<void>} - A promise that resolves when the new activity is fetched and added successfully.
         */
        async fetchUserFollowersCountAccepted(){
            try {
                this.userFollowersAccepted = await followers.getUserFollowersCountAccepted(this.userMe.id);
            } catch (error) {
                console.error("Failed to fetch data:", error);
            }
        },
        /**
         * Fetches the count of users being followed by the current user.
         * @async
         * @function fetchUserFollowingCountAll
         * @memberof module:stores/user
         * @throws {Error} If there is an error while fetching the data.
         * @returns {Promise<void>} - A promise that resolves when the new activity is fetched and added successfully.
         */
        async fetchUserFollowingCountAll(){
            try {
                this.userFollowingAll = await followers.getUserFollowingCountAll(this.userMe.id);
            } catch (error) {
                console.error("Failed to fetch data:", error);
            }
        },
        /**
         * Fetches the count of accepted user followings.
         * @async
         * @function fetchUserFollowingCountAccepted
         * @memberof module:stores/user
         * @throws {Error} If there is an error while fetching the data.
         * @returns {Promise<void>} - A promise that resolves when the new activity is fetched and added successfully.
         */
        async fetchUserFollowingCountAccepted(){
            try {
                this.userFollowingAccepted = await followers.getUserFollowingCountAccepted(this.userMe.id);
            } catch (error) {
                console.error("Failed to fetch data:", error);
            }
        }
    }
});