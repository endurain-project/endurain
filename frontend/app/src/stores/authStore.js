import { defineStore } from 'pinia';

import { API_URL } from "@/utils/serviceUtils";

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
        session_id: '',
    }),
    actions: {
        setUser(userData, session_id, locale) {
            this.user = userData;
            localStorage.setItem('user', JSON.stringify(this.user));
            localStorage.setItem('session_id', session_id);
            this.isAuthenticated = true;
            this.setUserWebsocket();
            this.session_id = session_id;
            
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
            this.session_id = '';
            localStorage.removeItem('user');
            localStorage.removeItem('session_id');

            this.setLocale('us', locale);
        },
        loadUserFromStorage(locale) {
            const storedUser = localStorage.getItem('user');
            if (storedUser) {
                this.user = JSON.parse(storedUser);
                this.isAuthenticated = true;
                this.setLocale(this.user.preferred_language, locale);
                this.setUserWebsocket();
                this.session_id = localStorage.getItem('session_id');
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
            const protocol = API_URL.startsWith('http://') ? 'ws' : 'wss';
            const websocketURL = `${API_URL}ws/${this.user.id}`;
            this.user_websocket = new WebSocket(websocketURL);
        },
    }
});