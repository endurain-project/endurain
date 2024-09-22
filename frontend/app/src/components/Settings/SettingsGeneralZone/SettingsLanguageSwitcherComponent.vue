<template>
    <form>
        <label for="langSelect" class="form-label">{{ $t("settingsLanguageSwitcher.formLabel") }}</label>
        <select class="form-select" id="langSelect" aria-label="Select for language picker">
            <option v-for="language in languages" :key="language.value" :value="language.value" :selected="currentLanguage == language.value" @click="changeLanguage(language.value)">{{ language.label }}</option>
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
            { value: 'us', label: 'English' },
            //{ value: 'pt', label: 'Portuguese' },
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

        const changeLanguage = (lang) => {
            setLanguage(lang);
            currentLanguage.value = lang;
        };

        onMounted(() => {
            currentLanguage.value = getPreferredLanguage();
            setLanguage(currentLanguage.value);
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