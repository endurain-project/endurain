import { fetchGetRequest, fetchPutRequest, fetchDeleteRequest } from '@/utils/serviceUtils';

export const garminConnect = {
    linkGarminConnect(data) {
        return fetchPutRequest("garminconnect/link", data)
    },
    getGarminConnectActivitiesLastDays(days) {
        return fetchGetRequest(`garminconnect/activities/days/${days}`);
    },
    getGarminConnectGear() {
        return fetchGetRequest('garminconnect/gear');
    },
    unlinkGarminConnect() {
        return fetchDeleteRequest('garminconnect/unlink');
    }
};