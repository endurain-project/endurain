<template>
  <div class="dropdown d-none d-lg-block">
    <!-- toggle with current theme -->
    <a
      class="nav-link link-body-emphasis dropdown-toggle"
      role="button"
      data-bs-toggle="dropdown"
      aria-expanded="false"
      aria-label="Theme switcher"
    >
      <font-awesome-icon :icon="['fas', 'moon']" v-if="themeStore.theme == 'dark'" />
      <font-awesome-icon :icon="['fas', 'sun']" v-else-if="themeStore.theme == 'light'" />
      <font-awesome-icon :icon="['fas', 'circle-half-stroke']" v-else />
    </a>

    <!-- dropdown menu -->
    <ul class="dropdown-menu">
      <li v-for="theme in themes" :key="theme.value">
        <a
          class="btn dropdown-item"
          @click="changeTheme(theme.value)"
          :aria-pressed="themeStore.theme === theme.value ? 'true' : 'false'"
          :aria-label="`Switch to ${theme.label} theme`"
        >
          <span v-if="theme.value == 'dark'" class="me-1"
            ><font-awesome-icon :icon="['fas', 'moon']"
          /></span>
          <span v-else-if="theme.value == 'light'"
            ><font-awesome-icon :icon="['fas', 'sun']"
          /></span>
          <span v-else><font-awesome-icon :icon="['fas', 'circle-half-stroke']" /></span>
          <span class="ms-2">{{ theme.label }}</span>
          <span v-if="themeStore.theme === theme.label.toLowerCase()" class="ms-3"
            ><font-awesome-icon :icon="['fas', 'check']"
          /></span>
        </a>
      </li>
    </ul>
  </div>
</template>

<script setup lang="ts">
/**
 * @fileoverview Theme switcher component for the navigation bar.
 * Provides a dropdown to switch between light, dark, and auto themes.
 * Automatically syncs with system theme preferences when auto mode is selected.
 */

// Section 1: Imports
import { onMounted, computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { useThemeStore } from '@/stores/themeStore'

// Section 2: Composables & Stores
const themeStore = useThemeStore()
const { t } = useI18n()

// Section 3: Reactive State
interface ThemeOption {
  value: string
  label: string
}

// Section 4: Computed Properties
const themes = computed<ThemeOption[]>(() => [
  { value: 'light', label: t('settingsThemeSwitcher.themeLight') },
  { value: 'dark', label: t('settingsThemeSwitcher.themeDark') },
  { value: 'auto', label: t('settingsThemeSwitcher.themeAuto') }
])

// Section 7: Main Logic
/**
 * Sets the theme on the document element.
 * For 'auto' theme, detects system preference.
 */
const setTheme = (theme: string): void => {
  if (theme === 'auto') {
    document.documentElement.setAttribute(
      'data-bs-theme',
      window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light'
    )
  } else {
    document.documentElement.setAttribute('data-bs-theme', theme)
  }
}

/**
 * Changes the current theme and persists it to the store.
 */
const changeTheme = (theme: string): void => {
  setTheme(theme)
  themeStore.setTheme(theme)
}

// Section 8: Lifecycle Hooks
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
</script>
