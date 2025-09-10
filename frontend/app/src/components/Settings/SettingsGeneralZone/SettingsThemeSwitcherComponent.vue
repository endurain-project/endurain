<template>
  <form>
    <label for="themeSelect" class="form-label">{{ $t('settingsThemeSwitcher.formLabel') }}</label>
    <select
      class="form-select"
      id="themeSelect"
      aria-label="Select for theme picker"
      v-model="themeStore.theme"
      @change="changeTheme"
    >
      <option v-for="theme in themes" :key="theme.value" :value="theme.value">
        {{ theme.label }}
      </option>
    </select>
  </form>
</template>

<script>
import { onMounted, watch, computed } from 'vue'
import { useI18n } from 'vue-i18n'

import { useThemeStore } from '@/stores/themeStore'

export default {
  setup() {
    const themeStore = useThemeStore()
    const { t } = useI18n()
    const themes = computed(() => [
      { value: 'light', label: t('settingsThemeSwitcher.themeLight') },
      { value: 'dark', label: t('settingsThemeSwitcher.themeDark') },
      { value: 'auto', label: t('settingsThemeSwitcher.themeAuto') }
    ])

    const setTheme = (theme) => {
      if (theme === 'auto') {
        document.documentElement.setAttribute(
          'data-bs-theme',
          window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light'
        )
      } else {
        document.documentElement.setAttribute('data-bs-theme', theme)
      }
    }

    const changeTheme = () => {
      setTheme(themeStore.theme)
      themeStore.setTheme(themeStore.theme)
    }

    onMounted(() => {
      setTheme(themeStore.theme)

      window.matchMedia('(prefers-color-scheme: dark)').addEventListener('change', () => {
        if (themeStore.theme !== 'light' && themeStore.theme !== 'dark') {
          const preferredTheme = window.matchMedia('(prefers-color-scheme: dark)').matches
            ? 'dark'
            : 'light'

          document.documentElement.setAttribute('data-bs-theme', preferredTheme)
        }
      })
    })

    watch(() => themeStore.theme, setTheme)

    return {
      themeStore,
      themes,
      changeTheme
    }
  }
}
</script>
