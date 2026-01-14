import {
  fetchGetRequest,
  fetchPostRequest,
  fetchPutRequest,
  fetchDeleteRequest,
  fetchPostFileRequest
} from '@/utils/serviceUtils'
import { fetchPublicGetRequest } from '@/utils/servicePublicUtils'

export const users = {
  // Users authenticated
  getUsersWithPagination(pageNumber, numRecords) {
    return fetchGetRequest(`users/page_number/${pageNumber}/num_records/${numRecords}`)
  },
  getUserContainsUsername(username) {
    return fetchGetRequest(`users/username/contains/${username}`)
  },
  getUserByUsername(username) {
    return fetchGetRequest(`users/username/${username}`)
  },
  getUserByEmail(email) {
    return fetchGetRequest(`users/email/${email}`)
  },
  getUserById(user_id) {
    return fetchGetRequest(`users/id/${user_id}`)
  },
  createUser(data) {
    return fetchPostRequest('users', data)
  },
  uploadImage(file, user_id) {
    const formData = new FormData()
    formData.append('file', file)

    return fetchPostFileRequest(`users/${user_id}/image`, formData)
  },
  editUser(user_id, data) {
    return fetchPutRequest(`users/${user_id}`, data)
  },
  approveUser(user_id) {
    return fetchPutRequest(`users/${user_id}/approve`)
  },
  editUserPassword(user_id, data) {
    return fetchPutRequest(`users/${user_id}/password`, data)
  },
  deleteUserPhoto(user_id) {
    return fetchDeleteRequest(`users/${user_id}/photo`)
  },
  deleteUser(user_id) {
    return fetchDeleteRequest(`users/${user_id}`)
  },
  // Users public
  getPublicUserById(user_id) {
    return fetchPublicGetRequest(`public/users/id/${user_id}`)
  }
}
