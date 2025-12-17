import {
  fetchGetRequest,
  fetchPostRequest,
  fetchPutRequest,
  fetchDeleteRequest,
  API_URL
} from '@/utils/serviceUtils'
import { fetchPublicGetRequest, fetchPublicPostRequest } from '@/utils/servicePublicUtils'

export const identityProviders = {
  getAllProviders() {
    return fetchGetRequest('idp')
  },
  getEnabledProviders() {
    return fetchPublicGetRequest('public/idp')
  },
  getTemplates() {
    return fetchGetRequest('idp/templates')
  },
  createProvider(data) {
    return fetchPostRequest('idp', data)
  },
  updateProvider(idpId, data) {
    return fetchPutRequest(`idp/${idpId}`, data)
  },
  deleteProvider(idpId) {
    return fetchDeleteRequest(`idp/${idpId}`)
  },
  initiateLogin(slug, params) {
    window.location.href = `${API_URL}public/idp/login/${slug}${params}`
  },
  exchangeSessionForTokens(sessionId, codeVerifier) {
    return fetchPublicPostRequest(`public/idp/session/${sessionId}/tokens`, {
      code_verifier: codeVerifier
    })
  }
}
