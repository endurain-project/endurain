import { defineStore } from 'pinia';
import { activities } from '@/services/activities';
import { followers } from '@/services/followers';
import { users } from '@/services/user';

// Function to get the default state
const getDefaultState = () => ({
    userMe: null,
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
});

export const useUserStore = defineStore('user', {
    state: getDefaultState,
    actions: {
        async fetchUserMe(user_id) {
            try {
                this.userMe = await users.getUserById(user_id);
            } catch (error) {
                console.error("Failed to fetch data:", error);
            }
        },
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
         * Fetches all followers of the user.
         * @async
         * @function fetchUserFollowersAll
         * @memberof module:stores/user
         * @instance
         * @throws {Error} If there is an error while fetching the data.
         */
        async fetchUserFollowersAll(){
            try {
                this.userFollowersAll = await followers.getUserFollowersAll(this.userMe.id);
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
                this.userFollowersCountAll = await followers.getUserFollowersCountAll(this.userMe.id);
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
                this.userFollowersCountAccepted = await followers.getUserFollowersCountAccepted(this.userMe.id);
            } catch (error) {
                console.error("Failed to fetch data:", error);
            }
        },
        /**
         * Fetches all the users that the current user is following.
         * @async
         * @function fetchUserFollowingAll
         * @memberof module:stores/user
         * @throws {Error} If there is an error while fetching the data.
         */
        async fetchUserFollowingAll(){
            try {
                this.userFollowingAll = await followers.getUserFollowingAll(this.userMe.id);
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
                this.userFollowingCountAll = await followers.getUserFollowingCountAll(this.userMe.id);
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
                this.userFollowingCountAccepted = await followers.getUserFollowingCountAccepted(this.userMe.id);
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