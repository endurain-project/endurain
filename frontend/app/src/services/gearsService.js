import { fetchGetRequest, fetchPostRequest, fetchPutRequest, fetchDeleteRequest } from '@/utils/serviceUtils';

export const gears = {
    getGearById(gearId) {
        return fetchGetRequest(`gears/id/${gearId}`);
    },
    getGearFromType(gearType) {
        return fetchGetRequest(`gears/type/${gearType}`);
    },
    getGearByNickname(nickname) {
        return fetchGetRequest(`gears/nickname/${nickname}`);
    },
    getUserGearsWithPagination(pageNumber, numRecords) {
        return fetchGetRequest(`gears/page_number/${pageNumber}/num_records/${numRecords}`);
    },
    getUserGearsNumber() {
        return fetchGetRequest('gears/number');
    },
    createGear(data) {
        return fetchPostRequest('gears/create', data)
    },
    editGear(gearId, data) {
        return fetchPutRequest(`gears/${gearId}/edit`, data);
    },
    deleteGear(gearId) {
        return fetchDeleteRequest(`gears/${gearId}/delete`);
    }
};