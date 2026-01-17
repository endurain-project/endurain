<template>
  <div class="row row-gap-3">
    <h1>{{ $t('settingsView.title') }}</h1>

    <!-- Include the SettingsSideBarComponent -->
    <SettingsSideBarComponent
      :activeSection="activeSection"
      @updateActiveSection="updateActiveSection"
    />

    <!-- Include the SettingsUserZone -->
    <SettingsUsersZone v-if="activeSection === 'users' && authStore.user.access_type === 'admin'" />

    <!-- Include the SettingsUserZone -->
    <SettingsServerSettingsZone
      v-if="activeSection === 'serverSettings' && authStore.user.access_type === 'admin'"
    />

    <!-- Include the SettingsIdentityProvidersZone -->
    <SettingsIdentityProvidersZone
      v-if="activeSection === 'identityProviders' && authStore.user.access_type === 'admin'"
    />

    <!-- Include the SettingsGeneralZone -->
    <SettingsGeneralZone v-if="activeSection === 'general'" />

    <!-- Include the SettingsUserProfileZone -->
    <SettingsUserProfileZone v-if="activeSection === 'myProfile'" />

    <!-- Include the SettingsSecurityZone -->
    <SettingsSecurityZone v-if="activeSection === 'security'" />

    <!-- Include the SettingsIntegrationsZone -->
    <SettingsIntegrationsZone v-if="activeSection === 'integrations'" />

    <!-- Include the SettingsUserGoals -->
    <SettingsUserGoals v-if="activeSection === 'myGoals'" />

    <!-- Include the SettingsImportZone -->
    <SettingsImportZone v-if="activeSection === 'import'" />
  </div>
  <!-- back button -->
  <BackButtonComponent />
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
// Importing the store
import { useAuthStore } from '@/stores/authStore'
// Import Notivue push
import { push } from 'notivue'
// Importing the services
import { strava } from '@/services/stravaService'
// Importing the components
import SettingsSideBarComponent from '../components/Settings/SettingsSideBarComponent.vue'
import SettingsUsersZone from '../components/Settings/SettingsUsersZone.vue'
import SettingsServerSettingsZone from '../components/Settings/SettingsServerSettingsZone.vue'
import SettingsIdentityProvidersZone from '../components/Settings/SettingsIdentityProvidersZone.vue'
import SettingsGeneralZone from '../components/Settings/SettingsGeneralZone.vue'
import SettingsUserProfileZone from '../components/Settings/SettingsUserProfileZone.vue'
import SettingsSecurityZone from '../components/Settings/SettingsSecurityZone.vue'
import SettingsIntegrationsZone from '../components/Settings/SettingsIntegrationsZone.vue'
import BackButtonComponent from '@/components/GeneralComponents/BackButtonComponent.vue'
import SettingsImportZone from '../components/Settings/SettingsImportZone.vue'
import SettingsUserGoals from '../components/Settings/SettingsUserGoals.vue'

const authStore = useAuthStore()
const route = useRoute()
const router = useRouter()
const { t } = useI18n()
const activeSection = ref('users')

/**
 * Updates the active section and updates the route query parameter.
 *
 * @param section - The section identifier to activate.
 */
function updateActiveSection(section: string): void {
  activeSection.value = section
  router.push({ query: { tab: section } })
}

onMounted(async () => {
  if (route.query.tab && typeof route.query.tab === 'string') {
    if (
      (route.query.tab === 'users' ||
        route.query.tab === 'serverSettings' ||
        route.query.tab === 'identityProviders') &&
      authStore.user.access_type === 'admin'
    ) {
      activeSection.value = route.query.tab
    } else if (
      (route.query.tab === 'users' ||
        route.query.tab === 'serverSettings' ||
        route.query.tab === 'identityProviders') &&
      authStore.user.access_type === 'regular'
    ) {
      activeSection.value = 'general'
    } else {
      activeSection.value = route.query.tab
    }
  }

  if (authStore.user.access_type === 'regular') {
    // If the user is not an admin, set the active section to general.
    activeSection.value = 'general'
  }

  if (route.query.stravaLinked === '1') {
    // If the stravaLinked query parameter is set to 1, set the active section to integrations.
    activeSection.value = 'integrations'

    // Set the user object with the strava_linked property set to 1.
    authStore.setStravaState(1)

    // Set the success message and show the success alert.
    push.success(t('settingsIntegrationsZone.successMessageStravaAccountLinked'))

    try {
      await strava.setUniqueUserStateStravaLink(null)
    } catch (error) {
      // If there is an error, set the error message and show the error alert.
      push.error(`${t('settingsIntegrationsZone.errorMessageUnableToUnSetStravaState')} - ${error}`)
    }
  }

  if (route.query.stravaLinked === '0') {
    // If the stravaLinked query parameter is set to 0, set the active section to integrations.
    activeSection.value = 'integrations'

    try {
      await strava.setUniqueUserStateStravaLink(null)

      // Set the user object with the strava_linked property set to 0.
      authStore.setStravaState(0)
    } catch (error) {
      // If there is an error, set the error message and show the error alert.
      push.error(`${t('settingsIntegrationsZone.errorMessageUnableToUnSetStravaState')} - ${error}`)
    }
  }
})
</script>
