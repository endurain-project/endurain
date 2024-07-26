import { createApp } from 'vue'
import { createPinia } from 'pinia'

import { useAuthStore } from './stores/authStore';
import { useThemeStore } from './stores/themeStore';

import "bootstrap/dist/css/bootstrap.min.css"
import 'bootstrap/dist/js/bootstrap.bundle.min.js';

import 'leaflet/dist/leaflet.css';

import App from './App.vue'
import router from './router'
import i18n from './i18n';

/* import the fontawesome core */
import { library } from '@fortawesome/fontawesome-svg-core';
/* import font awesome icon component */
import { FontAwesomeIcon } from '@fortawesome/vue-fontawesome';

/* import icons */
import { fas } from '@fortawesome/free-solid-svg-icons';
import { fab } from '@fortawesome/free-brands-svg-icons';
import { far } from '@fortawesome/free-regular-svg-icons';

/* add icons to the library */
library.add(fas, fab, far);

const app = createApp(App)

app.use(createPinia())
app.component('font-awesome-icon', FontAwesomeIcon)
app.use(router)
app.use(i18n);

// Import the store and load the user from the storage
const authStore = useAuthStore();
authStore.loadUserFromStorage(i18n);

const themeStore = useThemeStore();
themeStore.loadThemeFromStorage();

app.mount('#app')