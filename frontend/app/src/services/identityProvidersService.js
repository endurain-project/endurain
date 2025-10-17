/**
 * Identity Providers API Service
 *
 * Handles all API calls related to external identity providers (SSO/OAuth/OIDC).
 */

import {
  fetchGetRequest,
  fetchPostRequest,
  fetchPutRequest,
  fetchDeleteRequest,
  API_URL
} from '@/utils/serviceUtils'
import { fetchPublicGetRequest } from '@/utils/servicePublicUtils'

export const identityProviders = {
  /**
   * Get all configured identity providers (admin only)
   * @returns {Promise} Array of identity providers
   */
  getAllProviders() {
    return fetchGetRequest('idp')
  },

  /**
   * Get list of enabled identity providers for login page (public)
   * @returns {Promise} Array of public identity provider info
   */
  getEnabledProviders() {
    return fetchPublicGetRequest('public/idp')
  },

  /**
   * Get list of pre-configured IdP templates (admin only)
   * @returns {Promise} Array of available templates
   */
  getTemplates() {
    return fetchGetRequest('idp/templates')
  },

  /**
   * Create a new identity provider (admin only)
   * @param {Object} data - Identity provider configuration
   * @param {string} data.name - Display name
   * @param {string} data.slug - URL-safe identifier
   * @param {string} data.provider_type - Type (oidc, oauth2, saml)
   * @param {boolean} data.enabled - Whether enabled
   * @param {string} data.client_id - OAuth2/OIDC client ID
   * @param {string} data.client_secret - OAuth2/OIDC client secret
   * @param {string} [data.issuer_url] - OIDC issuer URL
   * @param {string} [data.scopes] - OAuth scopes
   * @param {string} [data.icon] - Icon name or URL
   * @param {boolean} [data.auto_create_users] - Auto-create users
   * @param {boolean} [data.sync_user_info] - Sync user info on login
   * @param {Object} [data.user_mapping] - Claims mapping
   * @returns {Promise} Created identity provider
   */
  createProvider(data) {
    return fetchPostRequest('idp', data)
  },

  /**
   * Update an existing identity provider (admin only)
   * @param {number} idpId - The identity provider ID
   * @param {Object} data - Updated identity provider configuration
   * @returns {Promise} Updated identity provider
   */
  updateProvider(idpId, data) {
    return fetchPutRequest(`idp/${idpId}`, data)
  },

  /**
   * Delete an identity provider (admin only)
   * @param {number} idpId - The identity provider ID
   * @returns {Promise}
   */
  deleteProvider(idpId) {
    return fetchDeleteRequest(`idp/${idpId}`)
  },

  /**
   * Initiate SSO login with a specific provider
   * Redirects browser to IdP authorization page
   * @param {string} slug - The provider slug
   */
  initiateLogin(slug) {
    window.location.href = `${API_URL}public/idp/login/${slug}`
  }
}
