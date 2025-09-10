// Importing the auth store
import { useAuthStore } from '@/stores/authStore'

let refreshTokenPromise = null

export const API_URL = `${window.env.ENDURAIN_HOST}/api/v1/`
export const FRONTEND_URL = `${window.env.ENDURAIN_HOST}/`

async function fetchWithRetry(url, options, responseType = 'json') {
  // Add CSRF token to headers for state-changing requests
  if (
    ['POST', 'PUT', 'DELETE', 'PATCH'].includes(options.method) &&
    url !== 'token' &&
    url !== 'refresh' &&
    url !== 'mfa/verify' &&
    url !== 'password-reset/request' &&
    url !== 'password-reset/confirm'
  ) {
    const csrfToken = document.cookie
      .split('; ')
      .find((row) => row.startsWith('endurain_csrf_token='))
      ?.split('=')[1]

    if (csrfToken) {
      options.headers = {
        ...options.headers,
        'X-CSRF-Token': csrfToken
      }
    }
  }

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
      try {
        await refreshAccessToken()
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
  return responseType === 'blob' ? response.blob() : response.json()
}

async function refreshAccessToken() {
  if (refreshTokenPromise) {
    return refreshTokenPromise
  }

  const refreshUrl = `${API_URL}refresh`
  refreshTokenPromise = fetch(refreshUrl, {
    method: 'POST',
    credentials: 'include',
    headers: {
      'Content-Type': 'application/json',
      'X-Client-Type': 'web'
    }
  })
    .then(async (response) => {
      if (!response.ok) {
        const errorBody = await response.json()
        const errorMessage = errorBody.detail || 'Unknown error'
        throw new Error(`${response.status} - ${errorMessage}`)
      }
    })
    .finally(() => {
      refreshTokenPromise = null
    })

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
