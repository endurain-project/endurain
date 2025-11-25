import {
  fetchGetRequest,
  fetchPostRequest,
  fetchPutRequest,
  fetchDeleteRequest
} from '@/utils/serviceUtils'

export const health_targets = {
  getUserHealthTargets() {
    return fetchGetRequest(`health_targets/`)
  },
  setUserHealthTargets(data) {
    return fetchPutRequest(`health_targets/`, data)
  }
}
