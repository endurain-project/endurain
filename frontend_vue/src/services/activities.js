import { fetchGetRequest, fetchPostFileRequest, fetchDeleteRequest, fetchPutRequest } from '@/utils/serviceUtils';

export const activities = {
    getUserThisWeekStats(user_id) {
        return fetchGetRequest(`activities/user/${user_id}/thisweek/distances`);
    },
    getUserThisMonthStats(user_id) {
        return fetchGetRequest(`activities/user/${user_id}/thismonth/distances`);
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