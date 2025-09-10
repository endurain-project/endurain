import {
  fetchGetRequest,
  fetchDeleteRequest,
  fetchPutRequest,
  fetchPostRequest
} from '@/utils/serviceUtils'

export const followers = {
  getUserFollowState(user_id, target_user_id) {
    return fetchGetRequest(`followers/user/${user_id}/targetUser/${target_user_id}`)
  },
  getUserFollowersAll(user_id) {
    return fetchGetRequest(`followers/user/${user_id}/followers/all`)
  },
  getUserFollowersCountAll(user_id) {
    return fetchGetRequest(`followers/user/${user_id}/followers/count/all`)
  },
  getUserFollowersCountAccepted(user_id) {
    return fetchGetRequest(`followers/user/${user_id}/followers/count/accepted`)
  },
  getUserFollowingAll(user_id) {
    return fetchGetRequest(`followers/user/${user_id}/following/all`)
  },
  getUserFollowingCountAll(user_id) {
    return fetchGetRequest(`followers/user/${user_id}/following/count/all`)
  },
  getUserFollowingCountAccepted(user_id) {
    return fetchGetRequest(`followers/user/${user_id}/following/count/accepted`)
  },
  deleteUserFollower(target_user_id) {
    return fetchDeleteRequest(`followers/delete/follower/targetUser/${target_user_id}`)
  },
  deleteUserFollowing(target_user_id) {
    return fetchDeleteRequest(`followers/delete/following/targetUser/${target_user_id}`)
  },
  createUserFollowsSpecificUser(target_user_id) {
    return fetchPostRequest(`followers/create/targetUser/${target_user_id}`)
  },
  acceptUserFollowsSpecificUser(target_user_id) {
    return fetchPutRequest(`followers/accept/targetUser/${target_user_id}`)
  }
}
