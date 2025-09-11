import {
  fetchGetRequest,
  fetchPostRequest,
} from '@/utils/serviceUtils'

export const signUp = {
  signUpRequest(userData) {
    return fetchPostRequest('sign-up/request', userData)
  },
  signUpConfirm(token) {
    return fetchGetRequest(`sign-up/confirm/${token}`)
  }
}
