import { fetchGetRequest } from '@/utils/serviceUtils';

export const activityStreams = {
    async getActivitySteamsByActivityId(activityId) {
        return fetchGetRequest(`activities/streams/activity_id/${activityId}/all`);
    },
    async getActivitySteamByStreamTypeByActivityId(activityId, streamType) {
        return fetchGetRequest(`activities/streams/activity_id/${activityId}/stream_type/${streamType}`);
    }
};