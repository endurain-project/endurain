import { fetchGetRequest, fetchPostRequest, fetchPutRequest, fetchDeleteRequest } from '@/utils/serviceUtils';

export const users = {
    getUsersWithPagination(pageNumber, numRecords) {
        return fetchGetRequest(`users/all/page_number/${pageNumber}/num_records/${numRecords}`);
    },
    getUsersNumber() {
        return fetchGetRequest('users/number');
    },
    getUserById(user_id) {
        return fetchGetRequest(`users/id/${user_id}`);
    },
    getUserByUsername(username){
        return fetchGetRequest(`users/username/contains/${username}`);
    },
    createUser(data) {
        return fetchPostRequest('users/create', data)
    },
    editUser(data) {
        return fetchPutRequest('users/edit', data)
    },
    editUserPassword(data) {
        return fetchPutRequest('users/edit/password', data)
    },
    deleteUser(user_id) {
        return fetchDeleteRequest(`users/${user_id}/delete`);
    }
};