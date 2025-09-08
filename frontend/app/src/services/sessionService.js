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
  signUpRequest(userData) {
    return fetchPostRequest('sign-up/request', userData)
  },
  signUpConfirm(token) {
    return fetchGetRequest(`sign-up/confirm/${token}`)
  }
}
