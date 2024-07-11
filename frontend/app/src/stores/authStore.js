import { defineStore } from 'pinia';

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
            access_type: null,
            photo_path: '',
            is_active: null,
            is_strava_linked: null,
        },
        isAuthenticated: false,
    }),
    actions: {
        setUser(userData, locale) {
            this.user = userData;
            localStorage.setItem('user', JSON.stringify(this.user));
            this.isAuthenticated = true;

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
                access_type: null,
                photo_path: '',
                is_active: null,
                is_strava_linked: null,
            };
            this.isAuthenticated = false;
            localStorage.removeItem('user');

            this.setLocale('en', locale);
        },
        loadUserFromStorage(locale) {
            const storedUser = localStorage.getItem('user');
            if (storedUser) {
                this.user = JSON.parse(storedUser);
                this.isAuthenticated = true;
                this.setLocale(this.user.locale, locale);
            }
        },
        setPreferredLanguage(language, locale) {
            this.user.locale = language;
            localStorage.setItem('user', JSON.stringify(this.user));

            this.setLocale(language, locale);
        },
        setLocale(language, locale) {
            locale.value = language;
            localStorage.setItem('lang', language);
        }
    }
});