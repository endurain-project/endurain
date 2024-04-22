import { fetchGetRequest, fetchPostFileRequest, fetchDeleteRequest, fetchPutRequest } from '@/utils/serviceUtils';

export const activities = {
    getUserWeekActivities(user_id, week_number) {
        return fetchGetRequest(`activities/user/${user_id}/week/${week_number}`);
    },
    getUserThisWeekStats(user_id) {
        return fetchGetRequest(`activities/user/${user_id}/thisweek/distances`);
    },
    getUserThisMonthStats(user_id) {
        return fetchGetRequest(`activities/user/${user_id}/thismonth/distances`);
    },
    getUserThisMonthActivitiesNumber(user_id) {
        return fetchGetRequest(`activities/user/${user_id}/thismonth/number`);
    },
    getUserActivitiesByGearId(user_id, gear_id) {
        return fetchGetRequest(`activities/user/${user_id}/gear/${gear_id}`);
    },
    getUserNumberOfActivities(user_id) {
        return fetchGetRequest(`activities/user/${user_id}/number`);
    },
    getUserActivitiesWithPagination(user_id, pageNumber, numRecords) {
        return fetchGetRequest(`activities/user/${user_id}/page_number/${pageNumber}/num_records/${numRecords}`);
    },
    getUserFollowersActivitiesWithPagination(user_id, pageNumber, numRecords) {
        return fetchGetRequest(`activities/user/${user_id}/followed/page_number/${pageNumber}/num_records/${numRecords}`);
    },
    getActivityById(activityId) {
        return fetchGetRequest(`activities/${activityId}`);
    },
    uploadActivityFile(formData) {
        return fetchPostFileRequest('activities/create/upload', formData);
    },
    addGearToActivity(activityId, gearId) {
        return fetchPutRequest(`activities/${activityId}/addgear/${gearId}`);
    },
    deleteGearFromActivity(activityId) {
        return fetchPutRequest(`activities/${activityId}/deletegear`);
    },
    deleteActivity(activityId) {
        return fetchDeleteRequest(`activities/${activityId}/delete`);
    }
};