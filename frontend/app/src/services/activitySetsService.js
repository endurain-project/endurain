import { fetchGetRequest } from '@/utils/serviceUtils';
import { fetchPublicGetRequest } from '@/utils/servicePublicUtils';

export const activitySets = {
    // Activity sets authenticated
    async getActivitySetsByActivityId(activityId) {
        return fetchGetRequest(`activities/sets/activity_id/${activityId}/all`);
    },
    // Activity sets public
    async getPublicActivitySetsByActivityId(activityId) {
        return fetchPublicGetRequest(`public/activities/sets/activity_id/${activityId}/all`);
    },
};