<template>
  <div class="col">
    <div class="bg-body-tertiary rounded p-3 shadow-sm">
      <SettingsThemeSwitcherComponent />
      <SettingsLanguageSwitcherComponent class="mt-2" />
    </div>
  </div>
</template>

<script>
import SettingsThemeSwitcherComponent from '@/components/Settings/SettingsGeneralZone/SettingsThemeSwitcherComponent.vue'
import SettingsLanguageSwitcherComponent from '@/components/Settings/SettingsGeneralZone/SettingsLanguageSwitcherComponent.vue'

export default {
  components: {
    SettingsThemeSwitcherComponent,
    SettingsLanguageSwitcherComponent
  },
  setup() {}
}
</script>
