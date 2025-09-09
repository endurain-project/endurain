import { fetchGetRequest, fetchPutRequest } from '@/utils/serviceUtils'

export const notifications = {
  getUserNotificationByID(notificationId) {
    return fetchGetRequest(`notifications/${notificationId}`)
  },
  getUserNotificationsNumber() {
    return fetchGetRequest('notifications/number')
  },
  getUserNotificationsWithPagination(pageNumber, numRecords) {
    return fetchGetRequest(`notifications/page_number/${pageNumber}/num_records/${numRecords}`)
  },
  markNotificationAsRead(notificationId) {
    return fetchPutRequest(`notifications/${notificationId}/mark_as_read`)
  }
}
