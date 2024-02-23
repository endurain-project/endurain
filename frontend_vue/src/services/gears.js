import { fetchGetRequest, fetchPostRequest, fetchPutRequest, fetchDeleteRequest } from '@/utils/serviceUtils';

export const gears = {
    getGearById(gearId) {
        return fetchGetRequest(`gear/id/${gearId}`);
    },
    getGearByNickname(nickname) {
        return fetchGetRequest(`gear/nickname/${nickname}`);
    },
    getUserGearsWithPagination(pageNumber, numRecords) {
        return fetchGetRequest(`gear/page_number/${pageNumber}/num_records/${numRecords}`);
    },
    getUserGearsNumber() {
        return fetchGetRequest('gear/number');
    },
    createGear(data) {
        return fetchPostRequest('gear/create', data)
    },
    editGear(gearId, data) {
        return fetchPutRequest(`gear/${gearId}/edit`, data);
    },
    deleteGear(gearId) {
        return fetchDeleteRequest(`gear/${gearId}/delete`);
    }
};