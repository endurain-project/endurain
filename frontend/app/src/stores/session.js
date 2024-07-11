import { defineStore } from 'pinia';

export const useSessionStore = defineStore('session', {
  state: () => ({
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
    photo_path_aux: null,
    is_active: null,
    is_strava_linked: null,
  }),
  actions: {
    setUser(user) {
      this.id = user.id;
      this.name = user.name;
      this.username = user.username;
      this.email = user.email;
      this.city = user.city;
      this.birthdate = user.birthdate;
      this.preferred_language = user.preferred_language;
      this.gender = user.gender;
      this.access_type = user.access_type;
      this.photo_path = user.photo_path;
      this.photo_path_aux = user.photo_path_aux;
      this.is_active = user.is_active;
      this.is_strava_linked = user.is_strava_linked;
    },
    resetUser() {
      this.$reset();
    }
  }
});