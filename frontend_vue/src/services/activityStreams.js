import { fetchGetRequest } from '@/utils/serviceUtils';

export const activityStreams = {
    async getActivitySteamByStreamTypeByActivityId(activityId, streamType) {
        return fetchGetRequest(`activities/streams/activity_id/${activityId}/stream_type/${streamType}`);
    }
};