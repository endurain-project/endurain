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
