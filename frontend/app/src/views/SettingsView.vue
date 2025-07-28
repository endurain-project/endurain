<template>
    <div class="row row-gap-3">
        <h1>{{ $t("settingsView.title") }}</h1>

        <!-- Include the SettingsSideBarComponent -->
        <SettingsSideBarComponent :activeSection="activeSection" @update-active-section="updateActiveSection" />

        <!-- Include the SettingsUserZone -->
        <SettingsUsersZone v-if="activeSection === 'users' && authStore.user.access_type == 2" />

        <!-- Include the SettingsUserZone -->
        <SettingsServerSettingsZone v-if="activeSection === 'serverSettings' && authStore.user.access_type == 2" />

        <!-- Include the SettingsGeneralZone -->
        <SettingsGeneralZone v-if="activeSection === 'general'" />

        <!-- Include the SettingsUserProfileZone -->
        <SettingsUserProfileZone v-if="activeSection === 'myProfile'" />

        <!-- Include the SettingsSecurityZone -->
        <SettingsSecurityZone v-if="activeSection === 'security'" />

        <!-- Include the SettingsIntegrationsZone -->
        <SettingsIntegrationsZone v-if="activeSection === 'integrations'" />

        <!-- Include the SettingsIntegrationsZone -->
        <SettingsImportZone v-if="activeSection === 'import'" />
    </div>
    <!-- back button -->
    <BackButtonComponent />
</template>

<script>
import { ref, onMounted } from 'vue';
import { useRoute } from 'vue-router';
import { useI18n } from 'vue-i18n';
// Importing the store
import { useAuthStore } from '@/stores/authStore';
// Import Notivue push
import { push } from 'notivue'
// Importing the services
import { strava } from '@/services/stravaService';
// Importing the components
import SettingsSideBarComponent from '../components/Settings/SettingsSideBarComponent.vue';
import SettingsUsersZone from '../components/Settings/SettingsUsersZone.vue';
import SettingsServerSettingsZone from '../components/Settings/SettingsServerSettingsZone.vue';
import SettingsGeneralZone from '../components/Settings/SettingsGeneralZone.vue';
import SettingsUserProfileZone from '../components/Settings/SettingsUserProfileZone.vue';
import SettingsSecurityZone from '../components/Settings/SettingsSecurityZone.vue';
import SettingsIntegrationsZone from '../components/Settings/SettingsIntegrationsZone.vue';
import SettingsImportZone from '../components/Settings/SettingsImportZone.vue';
import BackButtonComponent from '@/components/GeneralComponents/BackButtonComponent.vue';

export default {
    components: {
        SettingsSideBarComponent,
        SettingsUsersZone,
        SettingsServerSettingsZone,
        SettingsGeneralZone,
        SettingsUserProfileZone,
        SettingsSecurityZone,
        SettingsIntegrationsZone,
        SettingsImportZone,
        BackButtonComponent,
    },
    setup () {
        const authStore = useAuthStore();
        const route = useRoute();
        const { locale, t } = useI18n();
        const activeSection = ref('users');

        function updateActiveSection(section) {
            // Update the active section.
            activeSection.value = section;
        }

        onMounted(async () => {
            if (authStore.user.access_type === 1) {
                // If the user is not an admin, set the active section to general.
                activeSection.value = 'general';
            }

            if (route.query.stravaLinked === '1') {
                // If the stravaLinked query parameter is set to 1, set the active section to integrations.
                activeSection.value = 'integrations';

                // Set the user object with the strava_linked property set to 1.
                const user = authStore.user;
                user.is_strava_linked = 1;
                authStore.setUser(user, locale);

                // Set the success message and show the success alert.
                push.success(t('settingsIntegrationsZone.successMessageStravaAccountLinked'))

                try {
                    await strava.setUniqueUserStateStravaLink(null);
                } catch (error) {
                    // If there is an error, set the error message and show the error alert.
                    push.error(`${t('settingsIntegrationsZone.errorMessageUnableToUnSetStravaState')} - ${error}`)
                }
            }

            if (route.query.stravaLinked === '0') {
                // If the stravaLinked query parameter is set to 0, set the active section to integrations.
                activeSection.value = 'integrations';

                try {
                    await strava.setUniqueUserStateStravaLink(null);
                } catch (error) {
                    // If there is an error, set the error message and show the error alert.
                    push.error(`${t('settingsIntegrationsZone.errorMessageUnableToUnSetStravaState')} - ${error}`)
                }
            }
        });

        return {
            authStore,
            activeSection,
            updateActiveSection,
            t,
        };
    },
};
</script>
