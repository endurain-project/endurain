import { fetchGetRequest, fetchPostRequest, fetchPutRequest, fetchDeleteRequest } from '@/utils/serviceUtils';

export const gearsComponents = {
    getGearComponentsByGearId(gearId) {
        return fetchGetRequest(`gears/components/gear_id/${gearId}`);
    },
    createGearComponent(data) {
        return fetchPostRequest('gears/components', data)
    },
    deleteGearComponent(gearComponentId) {
        return fetchDeleteRequest(`gears/components/${gearComponentId}`);
    }
};