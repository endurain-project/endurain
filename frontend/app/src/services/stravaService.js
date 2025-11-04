import {
  fetchGetRequest,
  fetchPostRequest,
  fetchPutRequest,
  fetchDeleteRequest
} from '@/utils/serviceUtils'

export const strava = {
  setUniqueUserStateStravaLink(state) {
    return fetchPutRequest(`strava/state/${state}`)
  },
  setUserStravaClientSettings(clientId, clientSecret) {
    const data = {
      client_id: clientId,
      client_secret: clientSecret
    }
    return fetchPutRequest('strava/client', data)
  },
  linkStrava(state, stravaClientId) {
    let redirectUri = `${window.env.ENDURAIN_HOST}`
    redirectUri = encodeURIComponent(redirectUri)
    const scope = 'read,read_all,profile:read_all,activity:read,activity:read_all'

    const stravaAuthUrl = `https://www.strava.com/oauth/authorize?client_id=${stravaClientId}&response_type=code&redirect_uri=${redirectUri}/strava/callback&approval_prompt=force&scope=${scope}&state=${state}`

    // Redirect to the Strava authorization URL
    window.location.href = stravaAuthUrl
  },
  importBikes() {
    return fetchPostRequest('strava/import/bikes')
  },
  importShoes() {
    return fetchPostRequest('strava/import/shoes')
  },
  linkStravaCallback(state, code, scope) {
    return fetchPutRequest(`strava/link?state=${state}&code=${code}&scope=${scope}`)
  },
  getStravaActivitiesByDates(startDate, endDate) {
    return fetchGetRequest(`strava/activities?start_date=${startDate}&end_date=${endDate}`)
  },
  getStravaGear() {
    return fetchGetRequest('strava/gear')
  },
  unlinkStrava() {
    return fetchDeleteRequest('strava/unlink')
  }
}
