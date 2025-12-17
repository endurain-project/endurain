import { attemptFetch } from './serviceUtils'

export async function fetchPublicGetRequest(url) {
  const options = {
    method: 'GET',
    headers: {
      'Content-Type': 'application/json',
      'X-Client-Type': 'web'
    }
  }
  return attemptFetch(url, options)
}

export async function fetchPublicPostRequest(url, data) {
  const options = {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'X-Client-Type': 'web'
    },
    body: JSON.stringify(data)
  }
  return attemptFetch(url, options)
}
