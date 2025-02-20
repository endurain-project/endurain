import { fetchGetRequest } from '@/utils/serviceUtils';
import { fetchPublicGetRequest } from '@/utils/servicePublicUtils';

export const activityStreams = {
    // Activity streams authenticated
    async getActivitySteamsByActivityId(activityId) {
        return fetchGetRequest(`activities/streams/activity_id/${activityId}/all`);
    },
    async getActivitySteamByStreamTypeByActivityId(activityId, streamType) {
        return fetchGetRequest(`activities/streams/activity_id/${activityId}/stream_type/${streamType}`);
    },
    // Activity streams public
    async getPublicActivityStreamsByActivityId(activityId) {
        return fetchPublicGetRequest(`public/activities/streams/activity_id/${activityId}/all`);
    },
    async getPublicActivitySteamByStreamTypeByActivityId(activityId, streamType) {
        return fetchPublicGetRequest(`public/activities/streams/activity_id/${activityId}/stream_type/${streamType}`);
    },
};