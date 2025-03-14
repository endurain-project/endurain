import { fetchGetRequest } from '@/utils/serviceUtils';
import { fetchPublicGetRequest } from '@/utils/servicePublicUtils';

export const activityLaps = {
    // Activity laps authenticated
    async getActivityLapsByActivityId(activityId) {
        return fetchGetRequest(`activities/laps/activity_id/${activityId}/all`);
    },
    // Activity laps public
    async getPublicActivityLapsByActivityId(activityId) {
        return fetchPublicGetRequest(`public/activities/laps/activity_id/${activityId}/all`);
    },
};