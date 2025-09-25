import {
  fetchGetRequest,
  fetchPostFileRequest,
  fetchDeleteRequest,
  fetchPutRequest,
  fetchPostRequest
} from '@/utils/serviceUtils'

export const activityMedia = {
  // Activity media authenticated
  getUserActivityMediaByActivityId(activity_id) {
    return fetchGetRequest(`activities_media/activity_id/${activity_id}`)
  },
  uploadActivityMediaFile(activity_id, file) {
    const formData = new FormData()
    formData.append('file', file)

    return fetchPostFileRequest(`activities_media/upload/activity_id/${activity_id}`, formData)
  },
  deleteActivityMedia(media_id) {
    return fetchDeleteRequest(`activities_media/${media_id}`)
  }
}
