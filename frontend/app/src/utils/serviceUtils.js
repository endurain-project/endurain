// Importing the auth store
import { useAuthStore } from '@/stores/authStore'

let refreshTokenPromise = null

export const API_URL = `${window.env.ENDURAIN_HOST}/api/v1/`
export const FRONTEND_URL = `${window.env.ENDURAIN_HOST}/`

// Helper function to get CSRF token from cookie
function getCsrfToken() {
  return document.cookie
    .split('; ')
    .find((row) => row.startsWith('endurain_csrf_token='))
    ?.split('=')[1]
}

// Helper function to add CSRF token to options if needed
function addCsrfTokenToOptions(url, options) {
  if (
    ['POST', 'PUT', 'DELETE', 'PATCH'].includes(options.method) &&
    url !== 'token' &&
    url !== 'refresh' &&
    url !== 'mfa/verify' &&
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
  // Add CSRF token to headers for state-changing requests
  options = addCsrfTokenToOptions(url, options)

  try {
    return await attemptFetch(url, options, responseType)
  } catch (error) {
    if (error.message.startsWith('401') && url !== 'token') {
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
        await refreshAccessToken()
        // Re-add CSRF token after refresh (new token was set in cookie)
        options = addCsrfTokenToOptions(url, options)
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
  const options = {
    method: 'POST',
    credentials: 'include',
    headers: {
      'Content-Type': 'application/json',
      'X-Client-Type': 'web'
    }
  }

  refreshTokenPromise = (async () => {
    try {
      const response = await attemptFetch(url, options)

      const authStore = useAuthStore()
      authStore.setUserSessionId(response.session_id)

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
