<template>
  <div class="dropdown d-none d-lg-block">
    <!-- toggle with current lang -->
    <a
      class="nav-link link-body-emphasis dropdown-toggle"
      role="button"
      data-bs-toggle="dropdown"
      aria-expanded="false"
    >
      <span
        :class="'fi fi-' + currentLanguage"
        v-if="!['ca', 'gl', 'sl', 'sv'].includes(currentLanguage)"
      ></span>
      <span class="fi fi-es-ct" v-else-if="currentLanguage === 'ca'"></span>
      <span class="fi fi-es-ga" v-else-if="currentLanguage === 'gl'"></span>
      <span class="fi fi-si" v-else-if="currentLanguage === 'sl'"></span>
      <span class="fi fi-se" v-else-if="currentLanguage === 'sv'"></span>
    </a>

    <!-- dropdown menu -->
    <ul class="dropdown-menu">
      <li v-for="language in languages" :key="language.value">
        <a
          class="btn dropdown-item"
          @click="changeLanguage(language.value)"
          :aria-pressed="currentLanguage === language.value ? 'true' : 'false'"
        >
          <span class="me-2">{{ language.label }}</span>
          <span
            :class="'fi fi-' + language.value"
            v-if="!['ca', 'gl', 'sl', 'sv'].includes(language.value)"
          ></span>
          <span class="fi fi-es-ct" v-else-if="language.value === 'ca'"></span>
          <span class="fi fi-es-ga" v-else-if="language.value === 'gl'"></span>
          <span class="fi fi-si" v-else-if="language.value === 'sl'"></span>
          <span class="fi fi-se" v-else-if="language.value === 'sv'"></span>
          <span v-if="currentLanguage === language.value" class="ms-3"
            ><font-awesome-icon :icon="['fas', 'check']"
          /></span>
        </a>
      </li>
    </ul>
  </div>
</template>

/** * @fileoverview Language switcher component for the navigation bar. * Allows users to select
their preferred language from a dropdown menu. * Persists language selection to localStorage and
syncs with vue-i18n. */
<script setup lang="ts">
// ===========================
// Imports
// ===========================
import { ref, onMounted, watch, computed } from 'vue'
import { useI18n } from 'vue-i18n'

// ===========================
// Types
// ===========================
interface Language {
  value: string
  label: string
}

// ===========================
// Composables
// ===========================
const { locale, t } = useI18n()

// ===========================
// Reactive State
// ===========================
const currentLanguage = ref<string>(locale.value)

// ===========================
// Computed Properties
// ===========================
const languages = computed<Language[]>(() => [
  { value: 'ca', label: t('generalItems.languageOption2') },
  { value: 'cn', label: t('generalItems.languageOption8') },
  { value: 'tw', label: t('generalItems.languageOption9') },
  { value: 'de', label: t('generalItems.languageOption4') },
  { value: 'fr', label: t('generalItems.languageOption5') },
  { value: 'gl', label: t('generalItems.languageOption10') },
  { value: 'it', label: t('generalItems.languageOption11') },
  { value: 'nl', label: t('generalItems.languageOption6') },
  { value: 'pt', label: t('generalItems.languageOption3') },
  { value: 'sl', label: t('generalItems.languageOption12') },
  { value: 'sv', label: t('generalItems.languageOption13') },
  { value: 'es', label: t('generalItems.languageOption7') },
  { value: 'us', label: t('generalItems.languageOption1') }
])

// ===========================
// Utility Functions
// ===========================
const getStoredLanguage = (): string | null => localStorage.getItem('lang')
const setStoredLanguage = (lang: string): void => localStorage.setItem('lang', lang)

const getPreferredLanguage = (): string => {
  const storedLanguage = getStoredLanguage()
  return storedLanguage ? storedLanguage : 'us'
}

// ===========================
// Main Logic
// ===========================
const setLanguage = (lang: string): void => {
  locale.value = lang
  setStoredLanguage(lang)
}

const changeLanguage = (lang: string): void => {
  setLanguage(lang)
  currentLanguage.value = lang
}

// ===========================
// Lifecycle Hooks
// ===========================
onMounted(() => {
  currentLanguage.value = getPreferredLanguage()
  setLanguage(currentLanguage.value)
})

watch(locale, (newLocale: string) => {
  currentLanguage.value = newLocale
})
</script>
