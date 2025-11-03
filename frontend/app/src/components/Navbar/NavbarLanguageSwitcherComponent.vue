<template>
  <div class="nav-item dropdown d-none d-lg-block">
    <!-- toggle with current lang -->
    <a
      class="nav-link link-body-emphasis dropdown-toggle"
      role="button"
      data-bs-toggle="dropdown"
      aria-expanded="false"
    >
      <span :class="'fi fi-' + currentLanguage" v-if="currentLanguage !== 'ca'"></span>
      <span class="fi fi-es-ct" v-else-if="currentLanguage === 'ca'"></span>
      <span class="fi fi-es-ga" v-else-if="currentLanguage === 'gl'"></span>
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
          <span :class="'fi fi-' + language.value" v-if="language.value !== 'ca' && language.value !== 'gl'"></span>
          <span class="fi fi-es-ct" v-else-if="language.value === 'ca'"></span>
          <span class="fi fi-es-ga" v-else-if="language.value === 'gl'"></span>
          <span v-if="currentLanguage === language.value" class="ms-3"
            ><font-awesome-icon :icon="['fas', 'check']"
          /></span>
        </a>
      </li>
    </ul>
  </div>
</template>

<script setup>
import { ref, onMounted, watch, computed } from 'vue'
import { useI18n } from 'vue-i18n'

const { locale, t } = useI18n()
const languages = computed(() => [
  { value: 'ca', label: t('generalItems.languageOption2') },
  { value: 'cn', label: t('generalItems.languageOption8') },
  { value: 'tw', label: t('generalItems.languageOption9') },
  { value: 'de', label: t('generalItems.languageOption4') },
  { value: 'fr', label: t('generalItems.languageOption5') },
  { value: 'gl', label: t('generalItems.languageOption10') },
  { value: 'it', label: t('generalItems.languageOption11') },
  { value: 'nl', label: t('generalItems.languageOption6') },
  { value: 'pt', label: t('generalItems.languageOption3') },
  { value: 'es', label: t('generalItems.languageOption7') },
  { value: 'us', label: t('generalItems.languageOption1') }
])
const currentLanguage = ref(locale.value)

const getStoredLanguage = () => localStorage.getItem('lang')
const setStoredLanguage = (lang) => localStorage.setItem('lang', lang)

const getPreferredLanguage = () => {
  const storedLanguage = getStoredLanguage()
  return storedLanguage ? storedLanguage : 'us'
}

const setLanguage = (lang) => {
  locale.value = lang
  setStoredLanguage(lang)
}

const changeLanguage = (lang) => {
  setLanguage(lang)
  currentLanguage.value = lang
}

onMounted(() => {
  currentLanguage.value = getPreferredLanguage()
  setLanguage(currentLanguage.value)
})

watch(locale, (newLocale) => {
  currentLanguage.value = newLocale
})
</script>
