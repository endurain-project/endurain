import {
  fetchGetRequest,
  fetchPostRequest,
  fetchPostFormUrlEncoded,
  fetchDeleteRequest
} from '@/utils/serviceUtils'

export const session = {
  authenticateUser(formData) {
    return fetchPostFormUrlEncoded('auth/login', formData)
  },
  verifyMFAAndLogin(data) {
    return fetchPostRequest('auth/mfa/verify', data)
  },
  logoutUser() {
    return fetchPostRequest('auth/logout', null)
  },
  refreshToken() {
    return fetchPostRequest('auth/refresh', null)
  },
  getUserSessions(userId) {
    return fetchGetRequest(`sessions/user/${userId}`)
  },
  deleteSession(sessionId, userId) {
    return fetchDeleteRequest(`sessions/${sessionId}/user/${userId}`)
  }
}
