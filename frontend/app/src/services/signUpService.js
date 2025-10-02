import { fetchGetRequest, fetchPostRequest } from '@/utils/serviceUtils'

export const signUp = {
  signUpRequest(data) {
    return fetchPostRequest('sign-up/request', data)
  },
  signUpConfirm(data) {
    return fetchPostRequest('sign-up/confirm', data)
  }
}
