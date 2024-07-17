import { fetchGetRequest, fetchPostRequest, fetchPutRequest, fetchDeleteRequest, fetchPostFileRequest } from '@/utils/serviceUtils';

export const profile = {
    getProfileInfo() {
        return fetchGetRequest('profile/');
    },
    uploadProfileImage(file) {
        const formData = new FormData();
        formData.append('file', file);

        return fetchPostFileRequest(`profile/upload/image`, formData);
    },
    editProfile(data) {
        return fetchPutRequest('profile/edit', data)
    },
    editProfilePassword(data) {
        return fetchPutRequest(`profile/edit/password`, data)
    },
    deleteProfilePhoto() {
        return fetchPutRequest(`profile/delete-photo`);
    },
};