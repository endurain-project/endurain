import { createI18n } from 'vue-i18n'

// Bundle only locale JSON files (root + nested), eagerly so they're in dist
const translationModules = {
  ...import.meta.glob('./{ca,cn,de,es,fr,gl,it,nl,pt,sl,sv,tw,us}/*.json', { eager: true }),
  ...import.meta.glob('./{ca,cn,de,es,fr,gl,it,nl,pt,sl,sv,tw,us}/**/*.json', { eager: true })
}

// Define available locales
const locales = ['ca', 'cn', 'de', 'es', 'fr', 'gl', 'it', 'nl', 'pt', 'sl', 'sv', 'tw', 'us']

// Define all component paths
const componentPaths = {
  // Activities component
  addGearToActivityModalComponent:
    'components/activities/modals/addGearToActivityModalComponent.json',
  editActivityModalComponent: 'components/activities/modals/editActivityModalComponent.json',
  activityBellowMPillsComponent: 'components/activities/activityBellowMPillsComponent.json',
  activityLapsComponent: 'components/activities/activityLapsComponent.json',
  activityMandAbovePillsComponent: 'components/activities/activityMandAbovePillsComponent.json',
  activityMapComponent: 'components/activities/activityMapComponent.json',
  activitySummaryComponent: 'components/activities/activitySummaryComponent.json',
  activityWorkoutStepsComponent: 'components/activities/activityWorkoutStepsComponent.json',
  activitiesTableComponent: 'components/activities/activitiesTableComponent.json',
  // Followers component
  followersListComponent: 'components/followers/followersListComponent.json',
  // Gears component
  gearComponentAddEditModalComponent: 'components/gears/gearComponentAddEditModalComponent.json',
  gearComponentListComponent: 'components/gears/gearComponentListComponent.json',
  gearsAddEditGearModalComponent: 'components/gears/gearsAddEditGearModalComponent.json',
  gearsListComponent: 'components/gears/gearsListComponent.json',
  // Health components
  healthWeightAddEditModalComponent:
    'components/health/healthWeightZone/healthWeightAddEditModalComponent.json',
  healthWeightListComponent: 'components/health/healthWeightZone/healthWeightListComponent.json',
  healthDashboardZoneComponent: 'components/health/healthDashboardZoneComponent.json',
  healthSideBarComponent: 'components/health/healthSideBarComponent.json',
  healthWeightZoneComponent: 'components/health/healthWeightZoneComponent.json',
  healthStepsZoneComponent: 'components/health/healthStepsZoneComponent.json',
  healthStepsListComponent: 'components/health/healthStepsZone/healthStepsListComponent.json',
  healthStepsAddEditModalComponent:
    'components/health/healthStepsZone/healthStepsAddEditModalComponent.json',
  healthSleepZoneComponent: 'components/health/healthSleepZoneComponent.json',
  healthSleepListComponent: 'components/health/healthSleepZone/healthSleepListComponent.json',
  healthSleepListTabsComponent:
    'components/health/healthSleepZone/healthSleepListTabsComponent.json',
  healthSleepAddEditModalComponent:
    'components/health/healthSleepZone/healthSleepAddEditModalComponent.json',
  healthRHRZoneComponent: 'components/health/healthRHRZoneComponent.json',
  // Navbar components
  navbarBottomMobileComponent: 'components/navbar/navbarBottomMobileComponent.json',
  navbarComponent: 'components/navbar/navbarComponent.json',
  // Notifications components
  adminNewSignUpApprovalRequestNotificationComponent:
    'components/notifications/adminNewSignUpApprovalRequestNotificationComponent.json',
  navbarNotificationsComponent: 'components/notifications/navbarNotificationsComponent.json',
  newAcceptedRequestNotificationComponent:
    'components/notifications/newAcceptedRequestNotificationComponent.json',
  newActivityDuplicateStartTimeNotificationComponent:
    'components/notifications/newActivityDuplicateStartTimeNotificationComponent.json',
  newActivityNotificationComponent:
    'components/notifications/newActivityNotificationComponent.json',
  newFollowerRequestNotificationComponent:
    'components/notifications/newFollowerRequestNotificationComponent.json',
  // Settings components
  settingsSideBar: 'components/settings/settingsSideBarComponent.json',
  settingsUsersZone: 'components/settings/settingsUsersZoneComponent.json',
  settingsThemeSwitcher:
    'components/settings/settingsGeneralZone/settingsThemeSwitcherComponent.json',
  settingsLanguageSwitcher:
    'components/settings/settingsGeneralZone/settingsLanguageSwitcherComponent.json',
  settingsUserProfileZone: 'components/settings/settingsUserProfileZoneComponent.json',
  settingsSecurityZone: 'components/settings/settingsSecurityZoneComponent.json',
  settingsIntegrationsZone: 'components/settings/settingsIntegrationsZoneComponent.json',
  settingsImportZone: 'components/settings/settingsImportZoneComponent.json',
  garminConnectLoginModalComponent:
    'components/settings/settingsIntegrationsZone/garminConnectLoginModalComponent.json',
  usersAddEditUserModalComponent:
    'components/settings/settingsUsersZone/usersAddEditUserModalComponent.json',
  usersChangeUserPasswordModalComponent:
    'components/settings/settingsUsersZone/usersChangeUserPasswordModalComponent.json',
  usersListComponent: 'components/settings/settingsUsersZone/usersListComponent.json',
  usersPasswordRequirementsComponent:
    'components/settings/settingsUsersZone/usersPasswordRequirementsComponent.json',
  userIdentityProviderListComponent:
    'components/settings/settingsUsersZone/userIdentityProviderListComponent.json',
  userSessionsListComponent:
    'components/settings/settingsUserSessionsZone/userSessionsListComponent.json',
  settingsServerSettingsZoneComponent:
    'components/settings/settingsServerSettingsZoneComponent.json',
  settingsIdentityProvidersZone: 'components/settings/settingsIdentityProvidersZoneComponent.json',
  identityProvidersAddEditModal:
    'components/settings/settingsIdentityProvidersZone/identityProvidersAddEditModalComponent.json',
  settingsUserGoalsZone: 'components/settings/settingsUserGoals.json',
  goalsListComponent: 'components/settings/settingsUserGoalsZone/goalsListComponent.json',
  goalsAddEditGoalModalComponent:
    'components/settings/settingsUserGoalsZone/goalsAddEditGoalModalComponent.json',
  // Users components
  userDistanceStats: 'components/users/userDistanceStatsComponent.json',
  userGoalsStatsComponent: 'components/users/userGoalsStatsComponent.json',
  // General components
  noItemsFoundComponent: 'components/noItemsFoundComponent.json',
  // General translations
  generalItems: 'generalItems.json',
  // Views
  homeView: 'homeView.json',
  loginView: 'loginView.json',
  gearsView: 'gears/gearsView.json',
  gearView: 'gears/gearView.json',
  stravaCallbackView: 'strava/stravaCallbackView.json',
  activityView: 'activityView.json',
  activityItems: 'activityItems.json',
  activitiesView: 'activitiesView.json',
  healthView: 'healthView.json',
  notFound: 'notFoundView.json',
  searchView: 'searchView.json',
  settingsView: 'settingsView.json',
  userView: 'userView.json',
  summaryView: 'summaryView.json',
  resetPassword: 'resetPassword.json',
  signupView: 'signupView.json',
  emailVerificationView: 'emailVerificationView.json'
}

// Reverse map: relative path -> semantic key
const pathToKey = Object.entries(componentPaths).reduce((acc, [key, rel]) => {
  acc[rel] = key
  return acc
}, {})

function buildMessages() {
  const messages = Object.fromEntries(locales.map((l) => [l, {}]))

  for (const [importPath, mod] of Object.entries(translationModules)) {
    // "./us/components/.../file.json" or "./us/homeView.json"
    const m = importPath.match(/^\.\/([^/]+)\/(.+)$/)
    if (!m) continue
    const locale = m[1]
    if (!locales.includes(locale)) continue

    const relPath = m[2]
    const key = pathToKey[relPath]
    if (!key) {
      // Uncomment for debugging unknown files:
      // console.warn(`[i18n] No mapping for ${locale}/${relPath}`);
      continue
    }

    const value = mod && mod.default ? mod.default : mod
    messages[locale][key] = value
  }

  // Optional: ensure every key exists for every locale (fallback-safe)
  for (const l of locales) {
    for (const k of Object.keys(componentPaths)) {
      if (!(k in messages[l])) messages[l][k] = {}
    }
  }

  return messages
}

const i18n = createI18n({
  legacy: false,
  locale: 'us',
  fallbackLocale: 'us',
  messages: buildMessages()
})

export default i18n
export async function setupI18n() {
  return i18n
}
