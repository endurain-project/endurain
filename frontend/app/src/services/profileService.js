import { fetchGetRequest, fetchPostRequest, fetchPutRequest, fetchDeleteRequest, fetchPostFileRequest } from '@/utils/serviceUtils';

export const profile = {
    getProfileInfo() {
        return fetchGetRequest('profile');
    },
    getProfileSessions() {
        return fetchGetRequest('profile/sessions');
    },
    uploadProfileImage(file) {
        const formData = new FormData();
        formData.append('file', file);

        return fetchPostFileRequest('profile/image', formData);
    },
    editProfile(data) {
        return fetchPutRequest('profile', data)
    },
    editProfilePassword(data) {
        return fetchPutRequest('profile/password', data)
    },
    deleteProfilePhoto() {
        return fetchPutRequest('profile/photo');
    },
    deleteProfileSession(session_id) {
        return fetchDeleteRequest(`profile/sessions/${session_id}`);
    }
};