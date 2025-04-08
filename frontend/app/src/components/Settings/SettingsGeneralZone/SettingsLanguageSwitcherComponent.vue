<template>
    <form>
        <label for="langSelect" class="form-label">{{ $t("settingsLanguageSwitcher.formLabel") }}</label>
        <select class="form-select" id="langSelect" aria-label="Select for language picker" v-model="currentLanguage" @change="changeLanguage">
            <option v-for="language in languages" :key="language.value" :value="language.value">{{ language.label }}</option>
        </select>
    </form>
</template>

<script>
import { ref, onMounted, watch } from 'vue';
import { useI18n } from 'vue-i18n';

export default {
    setup() {
        const { locale } = useI18n();
        const languages = [
            { value: 'ca', label: 'Catalan' },
            { value: 'de', label: 'German' },
            { value: 'fr', label: 'French (FR)' },
            { value: 'nl', label: 'Dutch (NL)' },
            { value: 'pt', label: 'Portuguese (PT)' },
            { value: 'es', label: 'Spanish (ES)' },
            { value: 'us', label: 'English (US)' },
        ];
        const currentLanguage = ref(locale.value);

        const getStoredLanguage = () => localStorage.getItem('lang');
        const setStoredLanguage = (lang) => localStorage.setItem('lang', lang);

        const getPreferredLanguage = () => {
            const storedLanguage = getStoredLanguage();
            return storedLanguage ? storedLanguage : 'us';
        };

        const setLanguage = (lang) => {
            locale.value = lang;
            setStoredLanguage(lang);
        };

        const changeLanguage = () => {
            setLanguage(currentLanguage.value);
        };

        onMounted(() => {
            const preferredLanguage = getPreferredLanguage();
            setLanguage(preferredLanguage);
        });

        watch(locale, (newLocale) => {
            currentLanguage.value = newLocale;
        });

        return {
            languages,
            currentLanguage,
            changeLanguage,
        };
    },
};
</script>