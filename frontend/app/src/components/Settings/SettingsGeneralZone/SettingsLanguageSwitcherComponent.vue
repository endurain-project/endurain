<template>
  <form>
    <label for="langSelect" class="form-label">{{
      $t('settingsLanguageSwitcher.formLabel')
    }}</label>
    <select
      class="form-select"
      id="langSelect"
      aria-label="Select for language picker"
      v-model="currentLanguage"
      @change="changeLanguage"
    >
      <option v-for="language in languages" :key="language.value" :value="language.value">
        {{ language.label }}
      </option>
    </select>
  </form>
</template>

<script>
import { ref, onMounted, watch, computed } from 'vue'
import { useI18n } from 'vue-i18n'

export default {
  setup() {
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
      { value: 'sl', label: t('generalItems.languageOption12') },
      { value: 'sv', label: t('generalItems.languageOption13') },
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

    const changeLanguage = () => {
      setLanguage(currentLanguage.value)
    }

    onMounted(() => {
      const preferredLanguage = getPreferredLanguage()
      setLanguage(preferredLanguage)
    })

    watch(locale, (newLocale) => {
      currentLanguage.value = newLocale
    })

    return {
      languages,
      currentLanguage,
      changeLanguage
    }
  }
}
</script>
