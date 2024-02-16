import { createI18n } from 'vue-i18n';

// Importing translations
import enNavbarComponent from './en/components/navbarComponent.json';
import enUserDistanceStatsComponent from './en/components/userDistanceStatsComponent.json';
import enNoItemsFoundComponent from './en/components/noItemsFoundComponent.json';
import enHomeView from './en/homeView.json';
import enLoginView from './en/loginView.json';

// Constructing the messages structure
const messages = {
  en: {
    navbar: enNavbarComponent,
    userDistanceStats: enUserDistanceStatsComponent,
    noItemsFoundComponent: enNoItemsFoundComponent,
    home: enHomeView,
    login: enLoginView,
  },
};

// Creating the Vue I18n instance
const i18n = createI18n({
  locale: 'en', // Default locale
  fallbackLocale: 'en', // Fallback locale
  messages,
});

export default i18n;