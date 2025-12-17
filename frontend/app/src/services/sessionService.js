import {
  fetchGetRequest,
  fetchPostRequest,
  fetchPostFormUrlEncoded,
  fetchDeleteRequest
} from '@/utils/serviceUtils'

export const session = {
  getUserSessions(userId) {
    return fetchGetRequest(`sessions/user/${userId}`)
  },
  deleteSession(sessionId, userId) {
    return fetchDeleteRequest(`sessions/${sessionId}/user/${userId}`)
  },
  authenticateUser(formData) {
    return fetchPostFormUrlEncoded('token', formData)
  },
  verifyMFAAndLogin(data) {
    return fetchPostRequest('mfa/verify', data)
  },
  logoutUser() {
    return fetchPostRequest('logout', null)
  },
  refreshToken() {
    return fetchPostRequest('refresh', null)
  }
}
