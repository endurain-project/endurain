import { defineStore } from 'pinia';

export const useAuthStore = defineStore('auth', {
    state: () => ({
        isLoggedIn: localStorage.getItem('accessToken') ? true : false,
    }),
    actions: {
        setUserLoggedIn(data) {
            this.isLoggedIn = true;

            // Save the access token and token type in localStorage
            localStorage.setItem('accessToken', data.access_token);
            localStorage.setItem('tokenType', data.token_type);
        },
        setUserLoggedOut() {
            this.isLoggedIn = false;

            // Clear localStorage items related to authentication
            localStorage.removeItem('accessToken');
            localStorage.removeItem('tokenType');
            localStorage.removeItem('userMe');
        },
        isTokenValid(token) {
            if (!token) {
                return false;
            }

            const payload = JSON.parse(atob(token.split('.')[1]));
            const exp = payload.exp;
            const currentTime = Math.floor(Date.now() / 1000); // Current time in seconds

            return exp > currentTime;
        },
    },
});