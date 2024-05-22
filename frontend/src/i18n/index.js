import { createI18n } from 'vue-i18n';

// Importing translations
// Navbar and footer components
import enNavbarComponent from './en/components/navbarComponent.json';
import enFooterComponent from './en/components/footerComponent.json';
// Activities component
import enUserDistanceStatsComponent from './en/components/activities/userDistanceStatsComponent.json';
import enActivitySummaryComponent from './en/components/activities/activitySummaryComponent.json';
// Followers component
import enFollowersListComponent from './en/components/followers/followersListComponent.json';
// Settings components
import enSettingsSideBarComponent from './en/components/settings/settingsSideBarComponent.json';
import enSettingsUsersZoneComponent from './en/components/settings/settingsUsersZoneComponent.json';
import enSettingsUserProfileZoneComponent from './en/components/settings/settingsUserProfileZoneComponent.json';
import enSettingsSecurityZoneComponent from './en/components/settings/settingsSecurityZoneComponent.json';
import enSettingsIntegrationsZoneComponent from './en/components/settings/settingsIntegrationsZoneComponent.json';
import enUsersListComponent from './en/components/settings/settingsUsersZone/usersListComponent.json';
// General components
import enNoItemsFoundComponent from './en/components/noItemsFoundComponent.json';
// General translations
import enGeneralItens from './en/generalItens.json'
// Views
import enHomeView from './en/homeView.json';
import enLoginView from './en/loginView.json';
import enGearsView from './en/gears/gearsView.json';
import enGearView from './en/gears/gearView.json';
import enActivityView from './en/activityView.json';
import enNotFoundView from './en/notFoundView.json';
import enUserView from './en/userView.json';

// Constructing the messages structure
const messages = {
  en: {
    navbar: enNavbarComponent,
    footer: enFooterComponent,
    userDistanceStats: enUserDistanceStatsComponent,
    activitySummary: enActivitySummaryComponent,
    followersListComponent: enFollowersListComponent,
    settingsSideBar: enSettingsSideBarComponent,
    settingsUsersZone: enSettingsUsersZoneComponent,
    settingsUserProfileZone: enSettingsUserProfileZoneComponent,
    settingsSecurityZone: enSettingsSecurityZoneComponent,
    settingsIntegrationsZone: enSettingsIntegrationsZoneComponent,
    usersListComponent: enUsersListComponent,
    noItemsFoundComponent: enNoItemsFoundComponent,
    generalItens: enGeneralItens,
    home: enHomeView,
    login: enLoginView,
    gears: enGearsView,
    gear: enGearView,
    activity: enActivityView,
    notFound: enNotFoundView,
    user: enUserView,
  },
};

// Creating the Vue I18n instance
const i18n = createI18n({
  legacy: false, // you must set `false`, to use Composition API
  locale: 'en', // Default locale
  fallbackLocale: 'en', // Fallback locale
  messages,
});

export default i18n;