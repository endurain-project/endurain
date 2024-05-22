<template>
    <ErrorToastComponent v-if="errorMessage" />
    <SuccessToastComponent v-if="successMessage" />

    <div class="row row-gap-3">
        <h1>Settings</h1>

        <!-- Include the SettingsSideBarComponent -->
        <SettingsSideBarComponent :activeSection="activeSection" @update-active-section="updateActiveSection" />

        <!-- Include the SettingsUserZone -->
        <SettingsUsersZone v-if="activeSection === 'users' && userMe.access_type == 2" />

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
// Importing the services
import { strava } from '@/services/strava';
// Importing the stores
import { useSuccessAlertStore } from '@/stores/Alerts/successAlert';
import { useErrorAlertStore } from '@/stores/Alerts/errorAlert';
// Importing the components
import ErrorToastComponent from '@/components/Toasts/ErrorToastComponent.vue';
import SuccessToastComponent from '@/components/Toasts/SuccessToastComponent.vue';
import SettingsSideBarComponent from '../components/Settings/SettingsSideBarComponent.vue';
import SettingsUsersZone from '../components/Settings/SettingsUsersZone.vue';
import SettingsUserProfileZone from '../components/Settings/SettingsUserProfileZone.vue';
import SettingsSecurityZone from '../components/Settings/SettingsSecurityZone.vue';
import SettingsIntegrationsZone from '../components/Settings/SettingsIntegrationsZone.vue';
import BackButtonComponent from '@/components/BackButtonComponent.vue';

export default {
    components: {
        ErrorToastComponent,
        SuccessToastComponent,
        SettingsSideBarComponent,
        SettingsUsersZone,
        SettingsUserProfileZone,
        SettingsSecurityZone,
        SettingsIntegrationsZone,
        BackButtonComponent,
    },
    setup () {
        const userMe = ref(JSON.parse(localStorage.getItem('userMe')));
        const route = useRoute();
        const successAlertStore = useSuccessAlertStore();
        const errorAlertStore = useErrorAlertStore();
        const successMessage = ref('');
        const errorMessage = ref('');
        const { t } = useI18n();
        const activeSection = ref('users');

        function updateActiveSection(section) {
            activeSection.value = section;
        }

        onMounted(async () => {
            if (userMe.value.access_type === 1) {
                activeSection.value = 'myProfile';
            }

            if (route.query.stravaLinked === '1') {
                activeSection.value = 'integrations';
                // Set the success message and show the success alert.
                successMessage.value = t('settingsIntegrationsZone.successMessageStravaAccountLinked');
                successAlertStore.setAlertMessage(successMessage.value);
                successAlertStore.setClosableState(true);

                try {
                    await strava.unsetUniqueUserStateStravaLink();
                } catch (error) {
                    // If there is an error, set the error message and show the error alert.
                    errorMessage.value = t('settingsIntegrationsZone.errorMessageUnableToUnSetStravaState') + " - " + error.toString();
                    errorAlertStore.setAlertMessage(errorMessage.value);
                }
            }
        });

        return {
            userMe,
            activeSection,
            updateActiveSection,
            successMessage,
            errorMessage,
            t,
        };
    },
};
</script>