import { fetchGetRequest, fetchPostFileRequest, fetchDeleteRequest, fetchPutRequest } from '@/utils/serviceUtils';

export const followers = {
    getUserFollowersCountAll(user_id) {
        return fetchGetRequest(`followers/user/${user_id}/followers/count/all`);
    },
    getUserFollowersCountAccepted(user_id) {
        return fetchGetRequest(`followers/user/${user_id}/followers/count/accepted`);
    },
    getUserFollowingCountAll(user_id) {
        return fetchGetRequest(`followers/user/${user_id}/following/count/all`);
    },
    getUserFollowingCountAccepted(user_id) {
        return fetchGetRequest(`followers/user/${user_id}/following/count/accepted`);
    }
};