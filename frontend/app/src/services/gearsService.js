import { fetchGetRequest, fetchPostRequest, fetchPutRequest, fetchDeleteRequest } from '@/utils/serviceUtils';

export const gears = {
    getGears() {
        return fetchGetRequest("gears");
    },
    getGearById(gearId) {
        return fetchGetRequest(`gears/id/${gearId}`);
    },
    getGearFromType(gearType) {
        return fetchGetRequest(`gears/type/${gearType}`);
    },
    getGearContainsNickname(nickname) {
        return fetchGetRequest(`gears/nickname/contains/${nickname}`);
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
        return fetchPostRequest('gears', data)
    },
    editGear(gearId, data) {
        return fetchPutRequest(`gears/${gearId}`, data);
    },
    deleteGear(gearId) {
        return fetchDeleteRequest(`gears/${gearId}`);
    }
};