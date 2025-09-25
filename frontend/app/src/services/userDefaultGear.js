import {
  fetchGetRequest,
  fetchPostRequest,
  fetchPutRequest,
  fetchDeleteRequest,
  fetchPostFileRequest
} from '@/utils/serviceUtils'

export const userDefaultGear = {
  getUserDefaultGear() {
    return fetchGetRequest('profile/default_gear')
  },
  editUserDefaultGear(data) {
    return fetchPutRequest('profile/default_gear', data)
  }
}
