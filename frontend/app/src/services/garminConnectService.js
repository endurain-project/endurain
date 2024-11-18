import { fetchGetRequest, fetchPutRequest } from '@/utils/serviceUtils';

export const garminConnect = {
    linkGarminConnect(data) {
        return fetchPutRequest("garminconnect/link", data)
    },
    getGarminConnectActivitiesLastDays(days) {
        return fetchGetRequest(`garminconnect/activities/days/${days}`);
    },
};