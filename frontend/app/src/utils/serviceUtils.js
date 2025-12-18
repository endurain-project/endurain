// Importing the auth store
import { useAuthStore } from '@/stores/authStore'

let refreshTokenPromise = null

export const API_URL = `${window.env.ENDURAIN_HOST}/api/v1/`
export const FRONTEND_URL = `${window.env.ENDURAIN_HOST}/`

// Helper function to get CSRF token from auth store (in-memory)
function getCsrfToken() {
  const authStore = useAuthStore()
  return authStore.getCsrfToken()
}

// Helper function to get access token from auth store (in-memory)
function getAccessToken() {
  const authStore = useAuthStore()
  return authStore.getAccessToken()
}

// Helper function to add authorization and CSRF headers
function addAuthHeaders(url, options) {
  // Add Authorization Bearer header for all authenticated requests
  // Skip public endpoints (login, password-reset, sign-up)
  if (
    url !== 'auth/login' &&
    url !== 'password-reset/request' &&
    url !== 'password-reset/confirm' &&
    url !== 'sign-up/request' &&
    url !== 'sign-up/confirm' &&
    !url.startsWith('public/')
  ) {
    const accessToken = getAccessToken()
    if (accessToken) {
      options.headers = {
        ...options.headers,
        Authorization: `Bearer ${accessToken}`
      }
    }
  }

  // Add CSRF token for state-changing requests
  if (
    ['POST', 'PUT', 'DELETE', 'PATCH'].includes(options.method) &&
    url !== 'auth/login' &&
    url !== 'auth/mfa/verify' &&
    url !== 'password-reset/request' &&
    url !== 'password-reset/confirm' &&
    url !== 'sign-up/request' &&
    url !== 'sign-up/confirm'
  ) {
    const csrfToken = getCsrfToken()
    if (csrfToken) {
      options.headers = {
        ...options.headers,
        'X-CSRF-Token': csrfToken
      }
    }
  }

  return options
}

async function fetchWithRetry(url, options, responseType = 'json') {
  // Add Authorization and CSRF headers
  options = addAuthHeaders(url, options)

  try {
    return await attemptFetch(url, options, responseType)
  } catch (error) {
    // Don't retry on 401 for: token, refresh, logout, MFA verify, or Garmin link errors
    if (
      error.message.startsWith('401') &&
      url !== 'auth/login' &&
      url !== 'auth/refresh' &&
      url !== 'auth/logout'
    ) {
      if (
        url === 'garminconnect/link' &&
        error.message.includes('There was an authentication error using Garmin Connect')
      ) {
        throw error
      }
      if (url === 'mfa/verify' && error.message.includes('Invalid MFA code')) {
        throw error
      }
      try {
        // Use auth store's refreshAccessToken which updates tokens in memory
        const authStore = useAuthStore()
        await authStore.refreshAccessToken()
        // Re-add auth headers after refresh (new tokens in memory)
        options = addAuthHeaders(url, options)
        return await attemptFetch(url, options, responseType)
      } catch {
        const authStore = useAuthStore()
        authStore.logoutUser()
        window.location.replace(`${FRONTEND_URL}login?sessionExpired=true`)
      }
    } else {
      throw error
    }
  }
}

export async function attemptFetch(url, options, responseType = 'json') {
  const fullUrl = `${API_URL}${url}`
  const response = await fetch(fullUrl, options)
  if (!response.ok) {
    const errorBody = await response.json()
    const errorMessage = errorBody.detail || 'Unknown error'
    throw new Error(`${response.status} - ${errorMessage}`)
  }

  // Handle 204 No Content - no body to parse
  if (response.status === 204) {
    return null
  }

  return responseType === 'blob' ? response.blob() : response.json()
}

async function refreshAccessToken() {
  if (refreshTokenPromise) {
    return refreshTokenPromise
  }

  const url = 'refresh'
  const authStore = useAuthStore()
  const csrfToken = authStore.getCsrfToken()

  const options = {
    method: 'POST',
    credentials: 'include',
    headers: {
      'Content-Type': 'application/json',
      'X-Client-Type': 'web'
    }
  }

  // Add CSRF token if available (optional on initial load, required for subsequent refreshes)
  if (csrfToken) {
    options.headers['X-CSRF-Token'] = csrfToken
  }

  refreshTokenPromise = (async () => {
    try {
      const response = await attemptFetch(url, options)

      // Update tokens in auth store
      if (response.access_token) {
        authStore.setAccessToken(response.access_token)
      }
      if (response.csrf_token) {
        authStore.setCsrfToken(response.csrf_token)
      }
      if (response.session_id) {
        authStore.setUserSessionId(response.session_id)
      }

      return response
    } catch (error) {
      throw error
    } finally {
      refreshTokenPromise = null
    }
  })()

  return refreshTokenPromise
}

export async function fetchGetRequest(url, options = {}) {
  const requestOptions = {
    method: 'GET',
    credentials: 'include',
    headers: {
      'Content-Type': 'application/json',
      'X-Client-Type': 'web'
    }
  }
  const responseType = options.responseType || 'json'
  return fetchWithRetry(url, requestOptions, responseType)
}

export async function fetchPostFileRequest(url, formData) {
  const options = {
    method: 'POST',
    body: formData,
    credentials: 'include',
    headers: {
      'X-Client-Type': 'web'
    }
  }
  return fetchWithRetry(url, options)
}

export async function fetchPostFormUrlEncoded(url, formData) {
  const urlEncodedData = new URLSearchParams(formData)
  const options = {
    method: 'POST',
    body: urlEncodedData,
    credentials: 'include',
    headers: {
      'Content-Type': 'application/x-www-form-urlencoded',
      'X-Client-Type': 'web'
    }
  }
  return fetchWithRetry(url, options)
}

export async function fetchPostRequest(url, data) {
  const options = {
    method: 'POST',
    body: JSON.stringify(data),
    credentials: 'include',
    headers: {
      'Content-Type': 'application/json',
      'X-Client-Type': 'web'
    }
  }
  return fetchWithRetry(url, options)
}

export async function fetchPutRequest(url, data) {
  const options = {
    method: 'PUT',
    body: JSON.stringify(data),
    credentials: 'include',
    headers: {
      'Content-Type': 'application/json',
      'X-Client-Type': 'web'
    }
  }
  return fetchWithRetry(url, options)
}

export async function fetchDeleteRequest(url) {
  const options = {
    method: 'DELETE',
    credentials: 'include',
    headers: {
      'Content-Type': 'application/json',
      'X-Client-Type': 'web'
    }
  }
  return fetchWithRetry(url, options)
}

export async function fetchGetRequestWithRedirect(url) {
  window.location.href = `${API_URL}${url}`
}
