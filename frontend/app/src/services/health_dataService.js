import { fetchGetRequest, fetchPostRequest, fetchPutRequest, fetchDeleteRequest } from '@/utils/serviceUtils';

export const health_data = {
    getUserHealthDataNumber() {
        return fetchGetRequest('health/number');
    },
    getUserHealthData() {
        return fetchGetRequest('health/');
    },
    getUserHealthDataWithPagination(pageNumber, numRecords) {
        return fetchGetRequest(`health/page_number/${pageNumber}/num_records/${numRecords}`);
    },
    createHealthData(data) {
        return fetchPostRequest('health', data)
    },
    createWeight(data) {
        return fetchPostRequest('health/weight', data)
    },
    editWeight(data) {
        return fetchPutRequest(`health/weight/${data.id}`, data)
    },
    deleteWeight(id) {
        return fetchDeleteRequest(`health/weight/${id}`)
    }
};