import {
  fetchGetRequest,
  fetchPostRequest,
  fetchPutRequest,
  fetchDeleteRequest
} from '@/utils/serviceUtils'

export const onelapfit = {
  linkOneLapFit(email, password) {
    const data = {
      email: email,
      password: password
    }
    return fetchPutRequest('onelapfit/link', data)
  },
  getOneLapFitActivitiesByDates(startDate, endDate) {
    return fetchGetRequest(`onelapfit/activities?start_date=${startDate}&end_date=${endDate}`)
  },
  unlinkOneLapFit() {
    return fetchDeleteRequest('onelapfit/unlink')
  }
}
