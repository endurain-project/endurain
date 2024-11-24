import { defineStore } from 'pinia';

import { BACKEND_URL } from "@/utils/serviceUtils";

export const useAuthStore = defineStore('auth', {
    state: () => ({
        user: {
            id: null,
            name: '',
            username: '',
            email: '',
            city: null,
            birthdate: null,
            preferred_language: '',
            gender: null,
            height: null,
            access_type: null,
            photo_path: '',
            is_active: null,
            is_strava_linked: null,
            is_garminconnect_linked: null,
        },
        isAuthenticated: false,
        user_websocket: null,
    }),
    actions: {
        setUser(userData, locale) {
            this.user = userData;
            localStorage.setItem('user', JSON.stringify(this.user));
            this.isAuthenticated = true;
            this.setUserWebsocket();
            
            this.setLocale(this.user.preferred_language, locale);
        },
        clearUser(locale) {
            this.user = {
                id: null,
                name: '',
                username: '',
                email: '',
                city: null,
                birthdate: null,
                preferred_language: '',
                gender: null,
                height: null,
                access_type: null,
                photo_path: '',
                is_active: null,
                is_strava_linked: null,
                is_garminconnect_linked: null,
            };
            this.isAuthenticated = false;
            this.user_websocket.close();
            this.user_websocket = null;
            localStorage.removeItem('user');

            this.setLocale('us', locale);
        },
        loadUserFromStorage(locale) {
            const storedUser = localStorage.getItem('user');
            if (storedUser) {
                this.user = JSON.parse(storedUser);
                this.isAuthenticated = true;
                this.setLocale(this.user.preferred_language, locale);
                this.setUserWebsocket();
            }
        },
        setPreferredLanguage(language, locale) {
            this.user.preferred_language = language;
            localStorage.setItem('user', JSON.stringify(this.user));

            this.setLocale(language, locale);
        },
        setLocale(language, locale) {
            locale.value = language;
            localStorage.setItem('lang', language);
        },
        setUserWebsocket() {
            console.log("Protocol is:", import.meta.env.VITE_BACKEND_PROTOCOL);
            const protocol = import.meta.env.VITE_BACKEND_PROTOCOL === 'https' ? 'wss' : 'ws';
            const websocketURL = `${protocol}://${BACKEND_URL}ws/${this.user.id}`;
            console.log("WebSocket URL:", websocketURL);
            this.user_websocket = new WebSocket(websocketURL);
        },
    }
});