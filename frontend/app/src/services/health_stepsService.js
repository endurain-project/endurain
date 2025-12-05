import {
  fetchGetRequest,
  fetchPostRequest,
  fetchPutRequest,
  fetchDeleteRequest
} from '@/utils/serviceUtils'

export const health_steps = {
  getUserHealthSteps() {
    return fetchGetRequest('health/steps')
  },
  getUserHealthStepsWithPagination(pageNumber, numRecords) {
    return fetchGetRequest(`health/steps/page_number/${pageNumber}/num_records/${numRecords}`)
  },
  createHealthSteps(data) {
    return fetchPostRequest('health/steps', data)
  },
  editHealthSteps(data) {
    return fetchPutRequest('health/steps', data)
  },
  deleteHealthSteps(healthStepsId) {
    return fetchDeleteRequest(`health/steps/${healthStepsId}`)
  }
}
