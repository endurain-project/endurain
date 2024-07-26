<template>
    <div class="col">
        <SettingsThemeSwitcherComponent />
        <SettingsLanguageSwitcherComponent class="mt-2"/>
    </div>
</template>

<script>
import SettingsThemeSwitcherComponent from '@/components/Settings/SettingsGeneralZone/SettingsThemeSwitcherComponent.vue';
import SettingsLanguageSwitcherComponent from '@/components/Settings/SettingsGeneralZone/SettingsLanguageSwitcherComponent.vue';

export default {
    components: {
        SettingsThemeSwitcherComponent,
        SettingsLanguageSwitcherComponent,
    },
    setup() {

    },
};
</script>