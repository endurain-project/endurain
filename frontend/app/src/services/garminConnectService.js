import { fetchGetRequest, fetchPutRequest } from '@/utils/serviceUtils';

export const garminConnect = {
    linkGarminConnect(data) {
        return fetchPutRequest("garminconnect/link", data)
    },
};