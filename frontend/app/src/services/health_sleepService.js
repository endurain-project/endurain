import {
    fetchGetRequest,
    fetchPostRequest,
    fetchPutRequest,
    fetchDeleteRequest
} from '@/utils/serviceUtils'

export const health_sleep = {
    getUserHealthSleep() {
        return fetchGetRequest('health/sleep')
    },
    getUserHealthSleepWithPagination(pageNumber, numRecords) {
        return fetchGetRequest(`health/sleep/page_number/${pageNumber}/num_records/${numRecords}`)
    },
    createHealthSleep(data) {
        return fetchPostRequest('health/sleep', data)
    },
    editHealthSleep(data) {
        return fetchPutRequest('health/sleep', data)
    },
    deleteHealthSleep(healthSleepId) {
        return fetchDeleteRequest(`health/sleep/${healthSleepId}`)
    }
}
