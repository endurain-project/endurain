import { fetchGetRequest } from '@/utils/serviceUtils';

export const users = {
    getUserById(user_id) {
        return fetchGetRequest(`users/id/${user_id}`);
    },
    getUserByUsername(username){
        return fetchGetRequest(`users/username/contains/${username}`);
    }
};