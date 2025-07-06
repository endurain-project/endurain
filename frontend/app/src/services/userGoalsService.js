import { fetchGetRequest, fetchPostRequest, fetchPutRequest, fetchDeleteRequest, fetchPostFileRequest } from '@/utils/serviceUtils';
import { fetchPublicGetRequest } from '@/utils/servicePublicUtils';

export const userGoals = {
    getUserGoals() {
        return fetchGetRequest('goals/results');
    }
}