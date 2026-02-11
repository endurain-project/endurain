import { fetchGetRequest } from '@/utils/serviceUtils'
import { fetchPublicGetRequest } from '@/utils/servicePublicUtils'

export const activityStreams = {
  // Activity streams authenticated
  async getActivitySteamsByActivityId(activityId) {
    return fetchGetRequest(`activities_streams/activity_id/${activityId}/all`)
  },
  async getActivitySteamByStreamTypeByActivityId(activityId, streamType) {
    return fetchGetRequest(`activities_streams/activity_id/${activityId}/stream_type/${streamType}`)
  },
  // New optimized endpoint for getting all map streams for a user
  async getMapStreamsForUser(userId) {
    return fetchGetRequest(`activities_streams/user_id/${userId}/stream_type/7`)
  },
  // Activity streams public
  async getPublicActivityStreamsByActivityId(activityId) {
    return fetchPublicGetRequest(`public/activities_streams/activity_id/${activityId}/all`)
  },
  async getPublicActivitySteamByStreamTypeByActivityId(activityId, streamType) {
    return fetchPublicGetRequest(
      `public/activities_streams/activity_id/${activityId}/stream_type/${streamType}`
    )
  }
}
