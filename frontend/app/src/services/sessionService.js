import { fetchPostRequest, fetchPostFormUrlEncoded } from '@/utils/serviceUtils';

export const session = {
    authenticateUser(formData) {
        return fetchPostFormUrlEncoded('token', formData);
    },
    logoutUser() {
        return fetchPostRequest('logout');
    },
};