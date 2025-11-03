import { fetchGetRequest, fetchDeleteRequest } from '@/utils/serviceUtils'

export const userIdentityProviders = {
  getUserIdentityProviders(userId) {
    return fetchGetRequest(`users/${userId}/identity-providers`)
  },
  deleteUserIdentityProvider(userId, idpId) {
    return fetchDeleteRequest(`users/${userId}/identity-providers/${idpId}`)
  }
}
