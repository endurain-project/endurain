import { fetchGetRequest, fetchPostRequest, fetchDeleteRequest } from '@/utils/serviceUtils'

export const garminConnect = {
  linkGarminConnect(data) {
    return fetchPostRequest('garminconnect/link', data)
  },
  mfaGarminConnect(data) {
    return fetchPostRequest('garminconnect/mfa', data)
  },
  getGarminConnectActivitiesLastDays(days) {
    return fetchGetRequest(`garminconnect/activities/days/${days}`)
  },
  getGarminConnectActivitiesByDates(startDate, endDate) {
    return fetchGetRequest(`garminconnect/activities?start_date=${startDate}&end_date=${endDate}`)
  },
  getGarminConnectGear() {
    return fetchGetRequest('garminconnect/gear')
  },
  getGarminConnectHealthDataLastDays(days) {
    return fetchGetRequest(`garminconnect/health/days/${days}`)
  },
  getGarminConnectHealthDataByDates(startDate, endDate) {
    return fetchGetRequest(`garminconnect/health?start_date=${startDate}&end_date=${endDate}`)
  },
  unlinkGarminConnect() {
    return fetchDeleteRequest('garminconnect/unlink')
  }
}
