import { fetchGetRequest, fetchPostFileRequest, fetchDeleteRequest, fetchPutRequest } from '@/utils/serviceUtils';

export const followers = {
    getUserFollowState(user_id, target_user_id) {
        return fetchGetRequest(`followers/user/${user_id}/targetUser/${target_user_id}`);
    },
    getUserFollowersAll(user_id) {
        return fetchGetRequest(`followers/user/${user_id}/followers/all`);
    },
    getUserFollowersCountAll(user_id) {
        return fetchGetRequest(`followers/user/${user_id}/followers/count/all`);
    },
    getUserFollowersCountAccepted(user_id) {
        return fetchGetRequest(`followers/user/${user_id}/followers/count/accepted`);
    },
    getUserFollowingAll(user_id) {
        return fetchGetRequest(`followers/user/${user_id}/following/all`);
    },
    getUserFollowingCountAll(user_id) {
        return fetchGetRequest(`followers/user/${user_id}/following/count/all`);
    },
    getUserFollowingCountAccepted(user_id) {
        return fetchGetRequest(`followers/user/${user_id}/following/count/accepted`);
    },
    deleteUserFollowsSpecificUser(user_id, target_user_id) {
        return fetchDeleteRequest(`followers/delete/user/${user_id}/targetUser/${target_user_id}`);
    },
    acceptUserFollowsSpecificUser(user_id, target_user_id) {
        return fetchPutRequest(`followers/accept/user/${user_id}/targetUser/${target_user_id}`);
    }
};