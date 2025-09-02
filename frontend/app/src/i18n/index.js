import { createI18n } from 'vue-i18n';

// Define available locales
const locales = ['ca', 'de', 'es', 'fr', 'nl', 'pt', 'us'];

// Define all component paths
const componentPaths = {
	// Activities component
	'addGearToActivityModalComponent': 'components/activities/modals/addGearToActivityModalComponent.json',
	'editActivityModalComponent': 'components/activities/modals/editActivityModalComponent.json',
	'activityBellowMPillsComponent': 'components/activities/activityBellowMPillsComponent.json',
	'activityLapsComponent': 'components/activities/activityLapsComponent.json',
	'activityMandAbovePillsComponent': 'components/activities/activityMandAbovePillsComponent.json',
	'activityMapComponent': 'components/activities/activityMapComponent.json',
	'activitySummaryComponent': 'components/activities/activitySummaryComponent.json',
	'activityWorkoutStepsComponent': 'components/activities/activityWorkoutStepsComponent.json',
	'activitiesTableComponent': 'components/activities/activitiesTableComponent.json',
	// Followers component
	'followersListComponent': 'components/followers/followersListComponent.json',
	// Gears component
	'gearComponentAddEditModalComponent': 'components/gears/gearComponentAddEditModalComponent.json',
	'gearComponentListComponent': 'components/gears/gearComponentListComponent.json',
	'gearsAddEditGearModalComponent': 'components/gears/gearsAddEditGearModalComponent.json',
	'gearsListComponent': 'components/gears/gearsListComponent.json',
	// Health components
	'healthWeightAddEditModalComponent': 'components/health/healthWeightZone/healthWeightAddEditModalComponent.json',
	'healthWeightListComponent': 'components/health/healthWeightZone/healthWeightListComponent.json',
	'healthDashboardZoneComponent': 'components/health/healthDashboardZoneComponent.json',
	'healthSideBarComponent': 'components/health/healthSideBarComponent.json',
	'healthWeightZoneComponent': 'components/health/healthWeightZoneComponent.json',
	// Navbar components
	'navbarBottomMobileComponent': 'components/navbar/navbarBottomMobileComponent.json',
	'navbarComponent': 'components/navbar/navbarComponent.json',
	// Notifications components
	'navbarNotificationsComponent': 'components/notifications/navbarNotificationsComponent.json',
	'newAcceptedRequestNotificationComponent': 'components/notifications/newAcceptedRequestNotificationComponent.json',
	'newActivityDuplicateStartTimeNotificationComponent': 'components/notifications/newActivityDuplicateStartTimeNotificationComponent.json',
	'newActivityNotificationComponent': 'components/notifications/newActivityNotificationComponent.json',
	'newFollowerRequestNotificationComponent': 'components/notifications/newFollowerRequestNotificationComponent.json',
	// Settings components
	'settingsSideBar': 'components/settings/settingsSideBarComponent.json',
	'settingsUsersZone': 'components/settings/settingsUsersZoneComponent.json',
	'settingsThemeSwitcher': 'components/settings/settingsGeneralZone/settingsThemeSwitcherComponent.json',
	'settingsLanguageSwitcher': 'components/settings/settingsGeneralZone/settingsLanguageSwitcherComponent.json',
	'settingsUserProfileZone': 'components/settings/settingsUserProfileZoneComponent.json',
	'settingsSecurityZone': 'components/settings/settingsSecurityZoneComponent.json',
	'settingsIntegrationsZone': 'components/settings/settingsIntegrationsZoneComponent.json',
	'garminConnectLoginModalComponent': 'components/settings/settingsIntegrationsZone/garminConnectLoginModalComponent.json',
	'usersAddEditUserModalComponent': 'components/settings/settingsUsersZone/usersAddEditUserModalComponent.json',
	'usersChangeUserPasswordModalComponent': 'components/settings/settingsUsersZone/usersChangeUserPasswordModalComponent.json',
	'usersListComponent': 'components/settings/settingsUsersZone/usersListComponent.json',
	'usersPasswordRequirementsComponent': 'components/settings/settingsUsersZone/usersPasswordRequirementsComponent.json',
	'userSessionsListComponent': 'components/settings/settingsUserSessionsZone/userSessionsListComponent.json',
	'settingsServerSettingsZoneComponent': 'components/settings/settingsServerSettingsZoneComponent.json',
	'settingsUserGoalsZone': 'components/settings/settingsUserGoals.json',
	'goalsListComponent': 'components/settings/settingsUserGoalsZone/goalsListComponent.json',
	'goalsAddEditGoalModalComponent': 'components/settings/settingsUserGoalsZone/goalsAddEditGoalModalComponent.json',
	// Users components
	'userDistanceStats': 'components/users/userDistanceStatsComponent.json',
	"userGoalsStatsComponent": "components/users/userGoalsStatsComponent.json",
	// General components
	'noItemsFoundComponent': 'components/noItemsFoundComponent.json',
	// General translations
	'generalItems': 'generalItems.json',
	// Views
	'homeView': 'homeView.json',
	'loginView': 'loginView.json',
	'gearsView': 'gears/gearsView.json',
	'gearView': 'gears/gearView.json',
	'stravaCallbackView': 'strava/stravaCallbackView.json',
	'activityView': 'activityView.json',
	'activityItems': 'activityItems.json',
	'activitiesView': 'activitiesView.json',
	'healthView': 'healthView.json',
	'notFound': 'notFoundView.json',
	'searchView': 'searchView.json',
	'settingsView': 'settingsView.json',
	'userView': 'userView.json',
	'summaryView': 'summaryView.json',
};

// Function to dynamically import all translations
async function loadTranslations() {
	const messages = {};

	for (const locale of locales) {
		messages[locale] = {};

		// Load all components for this locale
		for (const [key, path] of Object.entries(componentPaths)) {
			try {
				const module = await import(/* @vite-ignore */ `./${locale}/${path}`);
				messages[locale][key] = module.default;
			} catch (error) {
				console.warn(`Failed to load ${locale}/${path}:`, error);
				// Fallback to empty object to prevent runtime errors
				messages[locale][key] = {};
			}
		}
	}

	return messages;
}

// Create i18n instance with lazy loading
let i18nInstance = null;

export async function setupI18n() {
	if (!i18nInstance) {
		const messages = await loadTranslations();

		i18nInstance = createI18n({
			legacy: false,
			locale: 'us',
			fallbackLocale: 'us',
			messages,
		});
	}

	return i18nInstance;
}

// For backward compatibility, export a default instance
// Note: This will be empty until setupI18n() is called
export default i18nInstance || createI18n({
	legacy: false,
	locale: 'us',
	fallbackLocale: 'us',
	messages: {},
});
