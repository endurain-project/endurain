<template>
    <div class="row row-gap-3">
        <h1>Settings</h1>

        <!-- Include the SettingsSideBarComponent -->
        <SettingsSideBarComponent :activeSection="activeSection" @update-active-section="updateActiveSection" />

        <!-- Include the SettingsUserZone -->
        <SettingsUsersZone v-if="activeSection === 'divUsers'" />

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
import { ref } from 'vue';
// Importing the components
import SettingsSideBarComponent from '../components/Settings/SettingsSideBarComponent.vue';
import SettingsUsersZone from '../components/Settings/SettingsUsersZone.vue';
import SettingsUserProfileZone from '../components/Settings/SettingsUserProfileZone.vue';
import SettingsSecurityZone from '../components/Settings/SettingsSecurityZone.vue';
import SettingsIntegrationsZone from '../components/Settings/SettingsIntegrationsZone.vue';
import BackButtonComponent from '@/components/BackButtonComponent.vue';

export default {
    components: {
        SettingsSideBarComponent,
        SettingsUsersZone,
        SettingsUserProfileZone,
        SettingsSecurityZone,
        SettingsIntegrationsZone,
        BackButtonComponent,
    },
    setup () {
        const activeSection = ref('divUsers');

        function updateActiveSection(section) {
            activeSection.value = section;
        }

        return {
            activeSection,
            updateActiveSection,
        };
    },
};
</script>