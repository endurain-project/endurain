import { fetchGetRequest, fetchPostRequest, fetchPutRequest, fetchDeleteRequest, fetchPostFileRequest } from '@/utils/serviceUtils';
import { fetchPublicGetRequest } from '@/utils/servicePublicUtils';

export const users = {
    // Users authenticated
    getUsersWithPagination(pageNumber, numRecords) {
        return fetchGetRequest(`users/all/page_number/${pageNumber}/num_records/${numRecords}`);
    },
    getUsersNumber() {
        return fetchGetRequest('users/number');
    },
    getUserById(user_id) {
        return fetchGetRequest(`users/id/${user_id}`);
    },
    getUserContainsUsername(username){
        return fetchGetRequest(`users/username/contains/${username}`);
    },
    getUserByUsername(username){
        return fetchGetRequest(`users/username/${username}`);
    },
    getUserByEmail(email){
        return fetchGetRequest(`users/email/${email}`);
    },
    createUser(data) {
        return fetchPostRequest('users/create', data)
    },
    uploadImage(file, user_id) {
        const formData = new FormData();
        formData.append('file', file);

        return fetchPostFileRequest(`users/${user_id}/upload/image`, formData);
    },
    editUser(user_id, data) {
        return fetchPutRequest(`users/${user_id}/edit`, data)
    },
    editUserPassword(user_id, data) {
        return fetchPutRequest(`users/${user_id}/edit/password`, data)
    },
    deleteUserPhoto(user_id) {
        return fetchPutRequest(`users/${user_id}/delete-photo`);
    },
    deleteUser(user_id) {
        return fetchDeleteRequest(`users/${user_id}/delete`);
    },
    // Users public
    getPublicUserById(user_id) {
        return fetchPublicGetRequest(`public/users/id/${user_id}`);
    },
};