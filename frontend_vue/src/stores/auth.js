import { defineStore } from 'pinia';

export const useAuthStore = defineStore('auth', {
    state: () => ({
        isLoggedIn: localStorage.getItem('accessToken') ? true : false,
    }),
    actions: {
        /**
         * Sets the user as logged in and saves the access token and token type in localStorage.
         * @param {Object} data - The data containing the access token and token type.
         */
        setUserLoggedIn(data) {
            // Set the user as logged in
            this.isLoggedIn = true;

            // Save the access token and token type in localStorage
            localStorage.setItem('accessToken', data.access_token);
            localStorage.setItem('tokenType', data.token_type);
        },
        /**
         * Sets the user as logged out and clears the localStorage items related to authentication.
         */
        setUserLoggedOut() {
            // Set the user as logged out
            this.isLoggedIn = false;

            // Clear localStorage items related to authentication
            localStorage.removeItem('accessToken');
            localStorage.removeItem('tokenType');
            localStorage.removeItem('userMe');
        },
        /**
         * Checks if a token is valid by comparing its expiration time with the current time.
         * @param {string} token - The token to be checked.
         * @returns {boolean} - True if the token is valid, false otherwise.
         */
        isTokenValid(token) {
            // If there is no token, it is not valid
            if (!token) {
                return false;
            }

            // Decode the token and get the expiration time
            const payload = JSON.parse(atob(token.split('.')[1]));
            const exp = payload.exp;
            // Get the current time in seconds
            const currentTime = Math.floor(Date.now() / 1000);

            // Return true if the expiration time is greater than the current time
            return exp > currentTime;
        },
    },
});