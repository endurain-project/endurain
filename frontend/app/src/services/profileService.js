import {
  fetchGetRequest,
  fetchPostRequest,
  fetchPutRequest,
  fetchDeleteRequest,
  fetchPostFileRequest,
  fetchGetRequestWithRedirect
} from '@/utils/serviceUtils'

export const profile = {
  getProfileInfo() {
    return fetchGetRequest('profile')
  },
  getProfileSessions() {
    return fetchGetRequest('profile/sessions')
  },
  uploadProfileImage(file) {
    const formData = new FormData()
    formData.append('file', file)

    return fetchPostFileRequest('profile/image', formData)
  },
  editProfile(data) {
    return fetchPutRequest('profile', data)
  },
  editUserPrivacySettings(data) {
    return fetchPutRequest('profile/privacy', data)
  },
  editProfilePassword(data) {
    return fetchPutRequest('profile/password', data)
  },
  deleteProfilePhoto() {
    return fetchPutRequest('profile/photo')
  },
  deleteProfileSession(session_id) {
    return fetchDeleteRequest(`profile/sessions/${session_id}`)
  },
  exportData() {
    return fetchGetRequest('profile/export', { responseType: 'blob' })
  },
  importData(file) {
    const formData = new FormData()
    formData.append('file', file)

    return fetchPostFileRequest('profile/import', formData)
  },
  // MFA endpoints
  getMFAStatus() {
    return fetchGetRequest('profile/mfa/status')
  },
  setupMFA() {
    return fetchPostRequest('profile/mfa/setup', {})
  },
  enableMFA(data) {
    return fetchPutRequest('profile/mfa/enable', data)
  },
  disableMFA(data) {
    return fetchPutRequest('profile/mfa/disable', data)
  },
  verifyMFA(data) {
    return fetchPostRequest('profile/mfa/verify', data)
  },
  // Backup codes endpoints
  getBackupCodeStatus() {
    return fetchGetRequest('profile/mfa/backup-codes/status')
  },
  regenerateBackupCodes() {
    return fetchPostRequest('profile/mfa/backup-codes', {})
  },
  getMyIdentityProviders() {
    return fetchGetRequest('profile/idp')
  },
  unlinkIdentityProvider(idpId) {
    return fetchDeleteRequest(`profile/idp/${idpId}`)
  },
  generateLinkToken(idpId) {
    return fetchPostRequest(`profile/idp/${idpId}/link/token`, {})
  },
  async linkIdentityProvider(idpId) {
    const response = await this.generateLinkToken(idpId)
    const linkToken = response.token

    fetchGetRequestWithRedirect(`profile/idp/${idpId}/link?link_token=${linkToken}`)
  }
}
