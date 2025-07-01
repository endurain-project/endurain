import { fetchGetRequest, fetchPostRequest, fetchPutRequest, fetchDeleteRequest } from '@/utils/serviceUtils';

export const notifications = {
    getUserNotificationsWithPagination(pageNumber, numRecords) {
        return fetchGetRequest(`notifications/page_number/${pageNumber}/num_records/${numRecords}`);
    },
};