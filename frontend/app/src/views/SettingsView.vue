<template>
    <div class="row row-gap-3">
        <h1>Settings</h1>

        <!-- Include the SettingsSideBarComponent -->
        <SettingsSideBarComponent :activeSection="activeSection" @update-active-section="updateActiveSection" />

        <!-- Include the SettingsUserZone -->
        <SettingsUsersZone v-if="activeSection === 'users' && authStore.user.access_type == 2" />

        <!-- Include the SettingsGeneralZone -->
        <SettingsGeneralZone v-if="activeSection === 'general'" />

        <!-- Include the SettingsUserProfileZone -->
        <SettingsUserProfileZone v-if="activeSection === 'myProfile'" />

        <!-- Include the SettingsSecurityZone -->
        <SettingsSecurityZone v-if="activeSection === 'security'" />

        <!-- Include the SettingsIntegrationsZone -->
        <SettingsIntegrationsZone v-if="activeSection === 'integrations'" />
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
// Importing the utils
import { addToast } from '@/utils/toastUtils';
// Importing the services
import { strava } from '@/services/stravaService';
// Importing the components
import SettingsSideBarComponent from '../components/Settings/SettingsSideBarComponent.vue';
import SettingsUsersZone from '../components/Settings/SettingsUsersZone.vue';
import SettingsGeneralZone from '../components/Settings/SettingsGeneralZone.vue';
import SettingsUserProfileZone from '../components/Settings/SettingsUserProfileZone.vue';
import SettingsSecurityZone from '../components/Settings/SettingsSecurityZone.vue';
import SettingsIntegrationsZone from '../components/Settings/SettingsIntegrationsZone.vue';
import BackButtonComponent from '@/components/GeneralComponents/BackButtonComponent.vue';

export default {
    components: {
        SettingsSideBarComponent,
        SettingsUsersZone,
        SettingsGeneralZone,
        SettingsUserProfileZone,
        SettingsSecurityZone,
        SettingsIntegrationsZone,
        BackButtonComponent,
    },
    setup () {
        const authStore = useAuthStore();
        const route = useRoute();
        const { t } = useI18n();
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
                user = authStore.user;
                user.strava_linked = 1;
                authStore.setUser(user);

                // Set the success message and show the success alert.
                addToast(t('settingsIntegrationsZone.successMessageStravaAccountLinked'), 'success', true);

                try {
                    await strava.unsetUniqueUserStateStravaLink();
                } catch (error) {
                    // If there is an error, set the error message and show the error alert.
                    addToast(t('settingsIntegrationsZone.errorMessageUnableToUnSetStravaState'), 'danger', true);
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