import { fetchGetRequest, fetchPostRequest, fetchPutRequest, fetchDeleteRequest } from '@/utils/serviceUtils';

export const segments = {
    createSegment(data) {
        return fetchPostRequest('segments', data);
    }
};