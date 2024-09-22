import { createI18n } from 'vue-i18n';

// Importing translations
// Navbar and footer components
import usNavbarComponent from './us/components/navbarComponent.json';
import usFooterComponent from './us/components/footerComponent.json';
// Activities component
import usUserDistanceStatsComponent from './us/components/activities/userDistanceStatsComponent.json';
import usActivitySummaryComponent from './us/components/activities/activitySummaryComponent.json';
import usEditActivityModalComponent from './us/components/activities/modals/editActivityModalComponent.json';
// Followers component
import usFollowersListComponent from './us/components/followers/followersListComponent.json';
// Health components
import usHealthSideBarComponent from './us/components/health/healthSideBarComponent.json';
// Settings components
import usSettingsSideBarComponent from './us/components/settings/settingsSideBarComponent.json';
import usSettingsUsersZoneComponent from './us/components/settings/settingsUsersZoneComponent.json';
import usSettingsThemeSwitcherComponent from './us/components/settings/settingsGeneralZone/settingsThemeSwitcherComponent.json';
import usSettingsLanguageSwitcherComponent from './us/components/settings/settingsGeneralZone/settingsLanguageSwitcherComponent.json';
import usSettingsUserProfileZoneComponent from './us/components/settings/settingsUserProfileZoneComponent.json';
import usSettingsSecurityZoneComponent from './us/components/settings/settingsSecurityZoneComponent.json';
import usSettingsIntegrationsZoneComponent from './us/components/settings/settingsIntegrationsZoneComponent.json';
import usUsersListComponent from './us/components/settings/settingsUsersZone/usersListComponent.json';
// General components
import usNoItemsFoundComponent from './us/components/noItemsFoundComponent.json';
// General translations
import usGeneralItems from './us/generalItems.json'
// Views
import usHomeView from './us/homeView.json';
import usLoginView from './us/loginView.json';
import usGearsView from './us/gears/gearsView.json';
import usGearView from './us/gears/gearView.json';
import usActivityView from './us/activityView.json';
import usHealthView from './us/healthView.json';
import usNotFoundView from './us/notFoundView.json';
import usUserView from './us/userView.json';
import usSettingsView from './us/settingsView.json';

// Constructing the messages structure
const messages = {
  us: {
    // Navbar and footer components
    navbar: usNavbarComponent,
    footer: usFooterComponent,
    // Activities component
    userDistanceStats: usUserDistanceStatsComponent,
    activitySummary: usActivitySummaryComponent,
    editActivityModalComponent: usEditActivityModalComponent,
    // Followers component
    followersListComponent: usFollowersListComponent,
    // Health components
    healthSideBar: usHealthSideBarComponent,
    // Settings components
    settingsSideBar: usSettingsSideBarComponent,
    settingsUsersZone: usSettingsUsersZoneComponent,
    settingsThemeSwitcher: usSettingsThemeSwitcherComponent,
    settingsLanguageSwitcher: usSettingsLanguageSwitcherComponent,
    settingsUserProfileZone: usSettingsUserProfileZoneComponent,
    settingsSecurityZone: usSettingsSecurityZoneComponent,
    settingsIntegrationsZone: usSettingsIntegrationsZoneComponent,
    usersListComponent: usUsersListComponent,
    // General components
    noItemsFoundComponent: usNoItemsFoundComponent,
    // General translations
    generalItems: usGeneralItems,
    // Views
    homeView: usHomeView,
    loginView: usLoginView,
    gearsView: usGearsView,
    gearView: usGearView,
    activity: usActivityView,
    healthView: usHealthView,
    notFound: usNotFoundView,
    settingsView: usSettingsView,
    userView: usUserView,
  },
};

// Creating the Vue I18n instance
const i18n = createI18n({
  legacy: false, // you must set `false`, to use Composition API
  locale: 'us', // Default locale
  fallbackLocale: 'us', // Fallback locale
  messages,
});

export default i18n;