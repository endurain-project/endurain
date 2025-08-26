import {
  fetchGetRequest,
  fetchPostRequest
} from '@/utils/serviceUtils'

export const mfa = {
  getMFAStatus() {
    return fetchGetRequest('mfa/status')
  },
  setupMFA() {
    return fetchPostRequest('mfa/setup', {})
  },
  enableMFA(data) {
    return fetchPostRequest('mfa/enable', data)
  },
  disableMFA(data) {
    return fetchPostRequest('mfa/disable', data)
  },
  verifyMFA(data) {
    return fetchPostRequest('mfa/verify', data)
  }
}