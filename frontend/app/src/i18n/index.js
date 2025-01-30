import { createI18n } from 'vue-i18n';

// Importing translations
// Catalan translations
// Navbar and footer components
import caNavbarComponent from './ca/components/navbarComponent.json';
import caFooterComponent from './ca/components/footerComponent.json';
// Activities component
import caUserDistanceStatsComponent from './ca/components/activities/userDistanceStatsComponent.json';
import caActivitySummaryComponent from './ca/components/activities/activitySummaryComponent.json';
import caEditActivityModalComponent from './ca/components/activities/modals/editActivityModalComponent.json';
// Followers component
import caFollowersListComponent from './ca/components/followers/followersListComponent.json';
// Gears component
import caGearsAddEditUserModalComponent from './ca/components/gears/gearsAddEditUserModalComponent.json';
// Health components
import caHealthWeightAddEditModalComponent from './ca/components/health/healthWeightZone/healthWeightAddEditModalComponent.json'
import caHealthWeightListComponent from './ca/components/health/healthWeightZone/healthWeightListComponent.json'
import caHealthDashboardZoneComponent from './ca/components/health/healthDashboardZoneComponent.json'
import caHealthSideBarComponent from './ca/components/health/healthSideBarComponent.json';
import caHealthWeightZoneComponent from './ca/components/health/healthWeightZoneComponent.json'
// Settings components
import caSettingsSideBarComponent from './ca/components/settings/settingsSideBarComponent.json';
import caSettingsUsersZoneComponent from './ca/components/settings/settingsUsersZoneComponent.json';
import caSettingsThemeSwitcherComponent from './ca/components/settings/settingsGeneralZone/settingsThemeSwitcherComponent.json';
import caSettingsLanguageSwitcherComponent from './ca/components/settings/settingsGeneralZone/settingsLanguageSwitcherComponent.json';
import caSettingsUserProfileZoneComponent from './ca/components/settings/settingsUserProfileZoneComponent.json';
import caSettingsSecurityZoneComponent from './ca/components/settings/settingsSecurityZoneComponent.json';
import caSettingsIntegrationsZoneComponent from './ca/components/settings/settingsIntegrationsZoneComponent.json';
import caGarminConnectLoginModalComponent from './ca/components/settings/settingsIntegrationsZone/garminConnectLoginModalComponent.json';
import caUsersAddEditUserModalComponent from './ca/components/settings/settingsUsersZone/usersAddEditUserModalComponent.json';
import caUsersListComponent from './ca/components/settings/settingsUsersZone/usersListComponent.json';
import caUserSessionsListComponent from './ca/components/settings/settingsUserSessionsZone/userSessionsListComponent.json';
// General components
import caNoItemsFoundComponent from './ca/components/noItemsFoundComponent.json';
// General translations
import caGeneralItems from './ca/generalItems.json'
// Views
import caHomeView from './ca/homeView.json';
import caLoginView from './ca/loginView.json';
import caGearsView from './ca/gears/gearsView.json';
import caGearView from './ca/gears/gearView.json';
import caStravaCallbackView from './ca/strava/stravaCallbackView.json';
import caActivityView from './ca/activityView.json';
import caHealthView from './ca/healthView.json';
import caNotFoundView from './ca/notFoundView.json';
import caUserView from './ca/userView.json';
import caSettingsView from './ca/settingsView.json';

// German translations
// Navbar and footer components
import deNavbarComponent from './de/components/navbarComponent.json';
import deFooterComponent from './de/components/footerComponent.json';
// Activities component
import deUserDistanceStatsComponent from './de/components/activities/userDistanceStatsComponent.json';
import deActivitySummaryComponent from './de/components/activities/activitySummaryComponent.json';
import deEditActivityModalComponent from './de/components/activities/modals/editActivityModalComponent.json';
// Followers component
import deFollowersListComponent from './de/components/followers/followersListComponent.json';
// Gears component
import deGearsAddEditUserModalComponent from './de/components/gears/gearsAddEditUserModalComponent.json';
// Health components
import deHealthWeightAddEditModalComponent from './de/components/health/healthWeightZone/healthWeightAddEditModalComponent.json'
import deHealthWeightListComponent from './de/components/health/healthWeightZone/healthWeightListComponent.json'
import deHealthDashboardZoneComponent from './de/components/health/healthDashboardZoneComponent.json'
import deHealthSideBarComponent from './de/components/health/healthSideBarComponent.json';
import deHealthWeightZoneComponent from './de/components/health/healthWeightZoneComponent.json'
// Settings components
import deSettingsSideBarComponent from './de/components/settings/settingsSideBarComponent.json';
import deSettingsUsersZoneComponent from './de/components/settings/settingsUsersZoneComponent.json';
import deSettingsThemeSwitcherComponent from './de/components/settings/settingsGeneralZone/settingsThemeSwitcherComponent.json';
import deSettingsLanguageSwitcherComponent from './de/components/settings/settingsGeneralZone/settingsLanguageSwitcherComponent.json';
import deSettingsUserProfileZoneComponent from './de/components/settings/settingsUserProfileZoneComponent.json';
import deSettingsSecurityZoneComponent from './de/components/settings/settingsSecurityZoneComponent.json';
import deSettingsIntegrationsZoneComponent from './de/components/settings/settingsIntegrationsZoneComponent.json';
import deGarminConnectLoginModalComponent from './de/components/settings/settingsIntegrationsZone/garminConnectLoginModalComponent.json';
import deUsersAddEditUserModalComponent from './de/components/settings/settingsUsersZone/usersAddEditUserModalComponent.json';
import deUsersListComponent from './de/components/settings/settingsUsersZone/usersListComponent.json';
import deUserSessionsListComponent from './de/components/settings/settingsUserSessionsZone/userSessionsListComponent.json';
// General components
import deNoItemsFoundComponent from './de/components/noItemsFoundComponent.json';
// General translations
import deGeneralItems from './de/generalItems.json'
// Views
import deHomeView from './de/homeView.json';
import deLoginView from './de/loginView.json';
import deGearsView from './de/gears/gearsView.json';
import deGearView from './de/gears/gearView.json';
import deStravaCallbackView from './de/strava/stravaCallbackView.json';
import deActivityView from './de/activityView.json';
import deHealthView from './de/healthView.json';
import deNotFoundView from './de/notFoundView.json';
import deUserView from './de/userView.json';
import deSettingsView from './de/settingsView.json';


// French translations
// Navbar and footer components
import frNavbarComponent from './fr/components/navbarComponent.json';
import frFooterComponent from './fr/components/footerComponent.json';
// Activities component
import frUserDistanceStatsComponent from './fr/components/activities/userDistanceStatsComponent.json';
import frActivitySummaryComponent from './fr/components/activities/activitySummaryComponent.json';
import frEditActivityModalComponent from './fr/components/activities/modals/editActivityModalComponent.json';
// Followers component
import frFollowersListComponent from './fr/components/followers/followersListComponent.json';
// Gears component
import frGearsAddEditUserModalComponent from './fr/components/gears/gearsAddEditUserModalComponent.json';
// Health components
import frHealthWeightAddEditModalComponent from './fr/components/health/healthWeightZone/healthWeightAddEditModalComponent.json'
import frHealthWeightListComponent from './fr/components/health/healthWeightZone/healthWeightListComponent.json'
import frHealthDashboardZoneComponent from './fr/components/health/healthDashboardZoneComponent.json'
import frHealthSideBarComponent from './fr/components/health/healthSideBarComponent.json';
import frHealthWeightZoneComponent from './fr/components/health/healthWeightZoneComponent.json'
// Settings components
import frSettingsSideBarComponent from './fr/components/settings/settingsSideBarComponent.json';
import frSettingsUsersZoneComponent from './fr/components/settings/settingsUsersZoneComponent.json';
import frSettingsThemeSwitcherComponent from './fr/components/settings/settingsGeneralZone/settingsThemeSwitcherComponent.json';
import frSettingsLanguageSwitcherComponent from './fr/components/settings/settingsGeneralZone/settingsLanguageSwitcherComponent.json';
import frSettingsUserProfileZoneComponent from './fr/components/settings/settingsUserProfileZoneComponent.json';
import frSettingsSecurityZoneComponent from './fr/components/settings/settingsSecurityZoneComponent.json';
import frSettingsIntegrationsZoneComponent from './fr/components/settings/settingsIntegrationsZoneComponent.json';
import frGarminConnectLoginModalComponent from './fr/components/settings/settingsIntegrationsZone/garminConnectLoginModalComponent.json';
import frUsersAddEditUserModalComponent from './fr/components/settings/settingsUsersZone/usersAddEditUserModalComponent.json';
import frUsersListComponent from './fr/components/settings/settingsUsersZone/usersListComponent.json';
import frUserSessionsListComponent from './fr/components/settings/settingsUserSessionsZone/userSessionsListComponent.json';
// General components
import frNoItemsFoundComponent from './fr/components/noItemsFoundComponent.json';
// General translations
import frGeneralItems from './fr/generalItems.json'
// Views
import frHomeView from './fr/homeView.json';
import frLoginView from './fr/loginView.json';
import frGearsView from './fr/gears/gearsView.json';
import frGearView from './fr/gears/gearView.json';
import frStravaCallbackView from './fr/strava/stravaCallbackView.json';
import frActivityView from './fr/activityView.json';
import frHealthView from './fr/healthView.json';
import frNotFoundView from './fr/notFoundView.json';
import frUserView from './fr/userView.json';
import frSettingsView from './fr/settingsView.json';


// Portuguese Portugal translations
// Navbar and footer components
import ptNavbarComponent from './pt/components/navbarComponent.json';
import ptFooterComponent from './pt/components/footerComponent.json';
// Activities component
import ptUserDistanceStatsComponent from './pt/components/activities/userDistanceStatsComponent.json';
import ptActivitySummaryComponent from './pt/components/activities/activitySummaryComponent.json';
import ptEditActivityModalComponent from './pt/components/activities/modals/editActivityModalComponent.json';
// Followers component
import ptFollowersListComponent from './pt/components/followers/followersListComponent.json';
// Gears component
import ptGearsAddEditUserModalComponent from './pt/components/gears/gearsAddEditUserModalComponent.json';
// Health components
import ptHealthWeightAddEditModalComponent from './pt/components/health/healthWeightZone/healthWeightAddEditModalComponent.json'
import ptHealthWeightListComponent from './pt/components/health/healthWeightZone/healthWeightListComponent.json'
import ptHealthDashboardZoneComponent from './pt/components/health/healthDashboardZoneComponent.json'
import ptHealthSideBarComponent from './pt/components/health/healthSideBarComponent.json';
import ptHealthWeightZoneComponent from './pt/components/health/healthWeightZoneComponent.json'
// Settings components
import ptSettingsSideBarComponent from './pt/components/settings/settingsSideBarComponent.json';
import ptSettingsUsersZoneComponent from './pt/components/settings/settingsUsersZoneComponent.json';
import ptSettingsThemeSwitcherComponent from './pt/components/settings/settingsGeneralZone/settingsThemeSwitcherComponent.json';
import ptSettingsLanguageSwitcherComponent from './pt/components/settings/settingsGeneralZone/settingsLanguageSwitcherComponent.json';
import ptSettingsUserProfileZoneComponent from './pt/components/settings/settingsUserProfileZoneComponent.json';
import ptSettingsSecurityZoneComponent from './pt/components/settings/settingsSecurityZoneComponent.json';
import ptSettingsIntegrationsZoneComponent from './pt/components/settings/settingsIntegrationsZoneComponent.json';
import ptGarminConnectLoginModalComponent from './pt/components/settings/settingsIntegrationsZone/garminConnectLoginModalComponent.json';
import ptUsersAddEditUserModalComponent from './pt/components/settings/settingsUsersZone/usersAddEditUserModalComponent.json';
import ptUsersListComponent from './pt/components/settings/settingsUsersZone/usersListComponent.json';
import ptUserSessionsListComponent from './pt/components/settings/settingsUserSessionsZone/userSessionsListComponent.json';
// General components
import ptNoItemsFoundComponent from './pt/components/noItemsFoundComponent.json';
// General translations
import ptGeneralItems from './pt/generalItems.json'
// Views
import ptHomeView from './pt/homeView.json';
import ptLoginView from './pt/loginView.json';
import ptGearsView from './pt/gears/gearsView.json';
import ptGearView from './pt/gears/gearView.json';
import ptStravaCallbackView from './pt/strava/stravaCallbackView.json';
import ptActivityView from './pt/activityView.json';
import ptHealthView from './pt/healthView.json';
import ptNotFoundView from './pt/notFoundView.json';
import ptUserView from './pt/userView.json';
import ptSettingsView from './pt/settingsView.json';

// US translations
// Navbar and footer components
import usNavbarComponent from './us/components/navbarComponent.json';
import usFooterComponent from './us/components/footerComponent.json';
// Activities component
import usUserDistanceStatsComponent from './us/components/activities/userDistanceStatsComponent.json';
import usActivitySummaryComponent from './us/components/activities/activitySummaryComponent.json';
import usEditActivityModalComponent from './us/components/activities/modals/editActivityModalComponent.json';
// Followers component
import usFollowersListComponent from './us/components/followers/followersListComponent.json';
// Gears component
import usGearsAddEditUserModalComponent from './us/components/gears/gearsAddEditUserModalComponent.json';
// Health components
import usHealthWeightAddEditModalComponent from './us/components/health/healthWeightZone/healthWeightAddEditModalComponent.json'
import usHealthWeightListComponent from './us/components/health/healthWeightZone/healthWeightListComponent.json'
import usHealthDashboardZoneComponent from './us/components/health/healthDashboardZoneComponent.json'
import usHealthSideBarComponent from './us/components/health/healthSideBarComponent.json';
import usHealthWeightZoneComponent from './us/components/health/healthWeightZoneComponent.json'
// Settings components
import usSettingsSideBarComponent from './us/components/settings/settingsSideBarComponent.json';
import usSettingsUsersZoneComponent from './us/components/settings/settingsUsersZoneComponent.json';
import usSettingsThemeSwitcherComponent from './us/components/settings/settingsGeneralZone/settingsThemeSwitcherComponent.json';
import usSettingsLanguageSwitcherComponent from './us/components/settings/settingsGeneralZone/settingsLanguageSwitcherComponent.json';
import usSettingsUserProfileZoneComponent from './us/components/settings/settingsUserProfileZoneComponent.json';
import usSettingsSecurityZoneComponent from './us/components/settings/settingsSecurityZoneComponent.json';
import usSettingsIntegrationsZoneComponent from './us/components/settings/settingsIntegrationsZoneComponent.json';
import usGarminConnectLoginModalComponent from './us/components/settings/settingsIntegrationsZone/garminConnectLoginModalComponent.json';
import usUsersAddEditUserModalComponent from './us/components/settings/settingsUsersZone/usersAddEditUserModalComponent.json';
import usUsersListComponent from './us/components/settings/settingsUsersZone/usersListComponent.json';
import usUserSessionsListComponent from './us/components/settings/settingsUserSessionsZone/userSessionsListComponent.json';
// General components
import usNoItemsFoundComponent from './us/components/noItemsFoundComponent.json';
// General translations
import usGeneralItems from './us/generalItems.json'
// Views
import usHomeView from './us/homeView.json';
import usLoginView from './us/loginView.json';
import usGearsView from './us/gears/gearsView.json';
import usGearView from './us/gears/gearView.json';
import usStravaCallbackView from './us/strava/stravaCallbackView.json';
import usActivityView from './us/activityView.json';
import usHealthView from './us/healthView.json';
import usNotFoundView from './us/notFoundView.json';
import usUserView from './us/userView.json';
import usSettingsView from './us/settingsView.json';

// Constructing the messages structure
const messages = {
  ca: {
    // Navbar and footer components
    navbar: caNavbarComponent,
    footer: caFooterComponent,
    // Activities component
    userDistanceStats: caUserDistanceStatsComponent,
    activitySummary: caActivitySummaryComponent,
    editActivityModalComponent: caEditActivityModalComponent,
    // Followers component
    followersListComponent: caFollowersListComponent,
    // Gears component
    gearsAddEditUserModalComponent: caGearsAddEditUserModalComponent,
    // Health components
    healthWeightAddEditModalComponent: caHealthWeightAddEditModalComponent,
    healthSideBarComponent: caHealthSideBarComponent,
    healthDashboardZoneComponent: caHealthDashboardZoneComponent,
    healthWeightZoneComponent: caHealthWeightZoneComponent,
    healthWeightListComponent: caHealthWeightListComponent,
    // Settings components
    settingsSideBar: caSettingsSideBarComponent,
    settingsUsersZone: caSettingsUsersZoneComponent,
    settingsThemeSwitcher: caSettingsThemeSwitcherComponent,
    settingsLanguageSwitcher: caSettingsLanguageSwitcherComponent,
    settingsUserProfileZone: caSettingsUserProfileZoneComponent,
    settingsSecurityZone: caSettingsSecurityZoneComponent,
    settingsIntegrationsZone: caSettingsIntegrationsZoneComponent,
    garminConnectLoginModalComponent: caGarminConnectLoginModalComponent,
    usersAddEditUserModalComponent: caUsersAddEditUserModalComponent,
    usersListComponent: caUsersListComponent,
    userSessionsListComponent: caUserSessionsListComponent,
    // General components
    noItemsFoundComponent: caNoItemsFoundComponent,
    // General translations
    generalItems: caGeneralItems,
    // Views
    homeView: caHomeView,
    loginView: caLoginView,
    gearsView: caGearsView,
    gearView: caGearView,
    stravaCallbackView: caStravaCallbackView,
    activity: caActivityView,
    healthView: caHealthView,
    notFound: caNotFoundView,
    settingsView: caSettingsView,
    userView: caUserView,
  },
  de: {
    // Navbar and footer components
    navbar: deNavbarComponent,
    footer: deFooterComponent,
    // Activities component
    userDistanceStats: deUserDistanceStatsComponent,
    activitySummary: deActivitySummaryComponent,
    editActivityModalComponent: deEditActivityModalComponent,
    // Followers component
    followersListComponent: deFollowersListComponent,
    // Gears component
    gearsAddEditUserModalComponent: deGearsAddEditUserModalComponent,
    // Health components
    healthWeightAddEditModalComponent: deHealthWeightAddEditModalComponent,
    healthSideBarComponent: deHealthSideBarComponent,
    healthDashboardZoneComponent: deHealthDashboardZoneComponent,
    healthWeightZoneComponent: deHealthWeightZoneComponent,
    healthWeightListComponent: deHealthWeightListComponent,
    // Settings components
    settingsSideBar: deSettingsSideBarComponent,
    settingsUsersZone: deSettingsUsersZoneComponent,
    settingsThemeSwitcher: deSettingsThemeSwitcherComponent,
    settingsLanguageSwitcher: deSettingsLanguageSwitcherComponent,
    settingsUserProfileZone: deSettingsUserProfileZoneComponent,
    settingsSecurityZone: deSettingsSecurityZoneComponent,
    settingsIntegrationsZone: deSettingsIntegrationsZoneComponent,
    garminConnectLoginModalComponent: deGarminConnectLoginModalComponent,
    usersAddEditUserModalComponent: deUsersAddEditUserModalComponent,
    usersListComponent: deUsersListComponent,
    userSessionsListComponent: deUserSessionsListComponent,
    // General components
    noItemsFoundComponent: deNoItemsFoundComponent,
    // General translations
    generalItems: deGeneralItems,
    // Views
    homeView: deHomeView,
    loginView: deLoginView,
    gearsView: deGearsView,
    gearView: deGearView,
    stravaCallbackView: deStravaCallbackView,
    activity: deActivityView,
    healthView: deHealthView,
    notFound: deNotFoundView,
    settingsView: deSettingsView,
    userView: deUserView,
  },
  fr: {
    // Navbar and footer components
    navbar: frNavbarComponent,
    footer: frFooterComponent,
    // Activities component
    userDistanceStats: frUserDistanceStatsComponent,
    activitySummary: frActivitySummaryComponent,
    editActivityModalComponent: frEditActivityModalComponent,
    // Followers component
    followersListComponent: frFollowersListComponent,
    // Gears component
    gearsAddEditUserModalComponent: frGearsAddEditUserModalComponent,
    // Health components
    healthWeightAddEditModalComponent: frHealthWeightAddEditModalComponent,
    healthSideBarComponent: frHealthSideBarComponent,
    healthDashboardZoneComponent: frHealthDashboardZoneComponent,
    healthWeightZoneComponent: frHealthWeightZoneComponent,
    healthWeightListComponent: frHealthWeightListComponent,
    // Settings components
    settingsSideBar: frSettingsSideBarComponent,
    settingsUsersZone: frSettingsUsersZoneComponent,
    settingsThemeSwitcher: frSettingsThemeSwitcherComponent,
    settingsLanguageSwitcher: frSettingsLanguageSwitcherComponent,
    settingsUserProfileZone: frSettingsUserProfileZoneComponent,
    settingsSecurityZone: frSettingsSecurityZoneComponent,
    settingsIntegrationsZone: frSettingsIntegrationsZoneComponent,
    garminConnectLoginModalComponent: frGarminConnectLoginModalComponent,
    usersAddEditUserModalComponent: frUsersAddEditUserModalComponent,
    usersListComponent: frUsersListComponent,
    userSessionsListComponent: frUserSessionsListComponent,
    // General components
    noItemsFoundComponent: frNoItemsFoundComponent,
    // General translations
    generalItems: frGeneralItems,
    // Views
    homeView: frHomeView,
    loginView: frLoginView,
    gearsView: frGearsView,
    gearView: frGearView,
    stravaCallbackView: frStravaCallbackView,
    activity: frActivityView,
    healthView: frHealthView,
    notFound: frNotFoundView,
    settingsView: frSettingsView,
    userView: frUserView,
  },
  pt: {
    // Navbar and footer components
    navbar: ptNavbarComponent,
    footer: ptFooterComponent,
    // Activities component
    userDistanceStats: ptUserDistanceStatsComponent,
    activitySummary: ptActivitySummaryComponent,
    editActivityModalComponent: ptEditActivityModalComponent,
    // Followers component
    followersListComponent: ptFollowersListComponent,
    // Gears component
    gearsAddEditUserModalComponent: ptGearsAddEditUserModalComponent,
    // Health components
    healthWeightAddEditModalComponent: ptHealthWeightAddEditModalComponent,
    healthSideBarComponent: ptHealthSideBarComponent,
    healthDashboardZoneComponent: ptHealthDashboardZoneComponent,
    healthWeightZoneComponent: ptHealthWeightZoneComponent,
    healthWeightListComponent: ptHealthWeightListComponent,
    // Settings components
    settingsSideBar: ptSettingsSideBarComponent,
    settingsUsersZone: ptSettingsUsersZoneComponent,
    settingsThemeSwitcher: ptSettingsThemeSwitcherComponent,
    settingsLanguageSwitcher: ptSettingsLanguageSwitcherComponent,
    settingsUserProfileZone: ptSettingsUserProfileZoneComponent,
    settingsSecurityZone: ptSettingsSecurityZoneComponent,
    settingsIntegrationsZone: ptSettingsIntegrationsZoneComponent,
    garminConnectLoginModalComponent: ptGarminConnectLoginModalComponent,
    usersAddEditUserModalComponent: ptUsersAddEditUserModalComponent,
    usersListComponent: ptUsersListComponent,
    userSessionsListComponent: ptUserSessionsListComponent,
    // General components
    noItemsFoundComponent: ptNoItemsFoundComponent,
    // General translations
    generalItems: ptGeneralItems,
    // Views
    homeView: ptHomeView,
    loginView: ptLoginView,
    gearsView: ptGearsView,
    gearView: ptGearView,
    stravaCallbackView: ptStravaCallbackView,
    activity: ptActivityView,
    healthView: ptHealthView,
    notFound: ptNotFoundView,
    settingsView: ptSettingsView,
    userView: ptUserView,
  },
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
    // Gears component
    gearsAddEditUserModalComponent: usGearsAddEditUserModalComponent,
    // Health components
    healthWeightAddEditModalComponent: usHealthWeightAddEditModalComponent,
    healthSideBarComponent: usHealthSideBarComponent,
    healthDashboardZoneComponent: usHealthDashboardZoneComponent,
    healthWeightZoneComponent: usHealthWeightZoneComponent,
    healthWeightListComponent: usHealthWeightListComponent,
    // Settings components
    settingsSideBar: usSettingsSideBarComponent,
    settingsUsersZone: usSettingsUsersZoneComponent,
    settingsThemeSwitcher: usSettingsThemeSwitcherComponent,
    settingsLanguageSwitcher: usSettingsLanguageSwitcherComponent,
    settingsUserProfileZone: usSettingsUserProfileZoneComponent,
    settingsSecurityZone: usSettingsSecurityZoneComponent,
    settingsIntegrationsZone: usSettingsIntegrationsZoneComponent,
    garminConnectLoginModalComponent: usGarminConnectLoginModalComponent,
    usersAddEditUserModalComponent: usUsersAddEditUserModalComponent,
    usersListComponent: usUsersListComponent,
    userSessionsListComponent: usUserSessionsListComponent,
    // General components
    noItemsFoundComponent: usNoItemsFoundComponent,
    // General translations
    generalItems: usGeneralItems,
    // Views
    homeView: usHomeView,
    loginView: usLoginView,
    gearsView: usGearsView,
    gearView: usGearView,
    stravaCallbackView: usStravaCallbackView,
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