import { fetchPostRequest } from '@/utils/serviceUtils'

export const passwordReset = {
  requestPasswordReset(data) {
    return fetchPostRequest('password-reset/request', data)
  },
  confirmPasswordReset(data) {
    return fetchPostRequest('password-reset/confirm', data)
  }
}
