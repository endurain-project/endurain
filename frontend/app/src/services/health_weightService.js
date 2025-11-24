import {
  fetchGetRequest,
  fetchPostRequest,
  fetchPutRequest,
  fetchDeleteRequest
} from '@/utils/serviceUtils'

export const health_weight = {
  getUserHealthWeightNumber() {
    return fetchGetRequest('health/weight/number')
  },
  getUserHealthWeight() {
    return fetchGetRequest('health/weight')
  },
  getUserHealthWeightWithPagination(pageNumber, numRecords) {
    return fetchGetRequest(`health/weight/page_number/${pageNumber}/num_records/${numRecords}`)
  },
  createHealthWeight(data) {
    return fetchPostRequest('health/weight', data)
  },
  editHealthWeight(data) {
    return fetchPutRequest('health/weight', data)
  },
  deleteHealthWeight(healthWeightId) {
    return fetchDeleteRequest(`health/weight/${healthWeightId}`)
  }
}
