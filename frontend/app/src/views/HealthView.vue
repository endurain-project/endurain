<template>
    <div class="row row-gap-3">
        <h1>{{ $t("healthView.title") }}</h1>

        <!-- Include the HealthSideBarComponent -->
        <HealthSideBarComponent :activeSection="activeSection" @update-active-section="updateActiveSection" />
    </div>
    <!-- back button -->
    <BackButtonComponent />
</template>

<script>
import { ref } from 'vue';
// Importing the components
import HealthSideBarComponent from '../components/Health/HealthSideBarComponent.vue';
import SettingsUsersZone from '../components/Settings/SettingsUsersZone.vue';
import SettingsGeneralZone from '../components/Settings/SettingsGeneralZone.vue';
import SettingsUserProfileZone from '../components/Settings/SettingsUserProfileZone.vue';
import SettingsSecurityZone from '../components/Settings/SettingsSecurityZone.vue';
import SettingsIntegrationsZone from '../components/Settings/SettingsIntegrationsZone.vue';
import BackButtonComponent from '@/components/GeneralComponents/BackButtonComponent.vue';

export default {
    components: {
        HealthSideBarComponent,
        SettingsUsersZone,
        SettingsGeneralZone,
        SettingsUserProfileZone,
        SettingsSecurityZone,
        SettingsIntegrationsZone,
        BackButtonComponent,
    },
    setup () {
        const activeSection = ref('dashboard');

        function updateActiveSection(section) {
            // Update the active section.
            activeSection.value = section;
        }

        return {
            activeSection,
            updateActiveSection,
        };
    },
};
</script>