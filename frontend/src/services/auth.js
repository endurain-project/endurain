import { fetchGetRequestTokenAsParameter, fetchPostFormUrlEncoded } from '@/utils/serviceUtils';
import { useUserStore } from '@/stores/user';

export const auth = {
    isTokenValid(token) {
        if (!token) {
            return false;
        }

        const payload = JSON.parse(atob(token.split('.')[1]));
        const exp = payload.exp;
        const currentTime = Math.floor(Date.now() / 1000);

        return exp > currentTime;
    },
    storeLoggedUser(token, userMe) {
        localStorage.setItem('accessToken', token.access_token);
        localStorage.setItem('tokenType', token.token_type);
        localStorage.setItem('userMe', JSON.stringify(userMe));
    },
    removeLoggedUser() {
        localStorage.clear();
        const userStore = useUserStore();
        userStore.resetStore();
        //this.$router.push('/login');
    },
    getToken(formData) {
        return fetchPostFormUrlEncoded('token', formData);
    },
    getUserMe(token) {
        return fetchGetRequestTokenAsParameter('users/me', token);
    },
};