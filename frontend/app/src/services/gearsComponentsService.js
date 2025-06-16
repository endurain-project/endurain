import { fetchGetRequest, fetchPostRequest, fetchPutRequest, fetchDeleteRequest } from '@/utils/serviceUtils';

export const gearsComponents = {
    getGearComponentsByGearId(gearId) {
        return fetchGetRequest(`gears/components/gear_id/${gearId}`);
    },
};