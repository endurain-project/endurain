import { fetchGetRequest, fetchPostFormUrlEncoded } from '@/utils/serviceUtils';

export const session = {
    getToken(formData) {
        return fetchPostFormUrlEncoded('token', formData);
    },
};