<template>
    <div class="nav-item dropdown d-none d-lg-block">
        <!-- toggle with current lang -->
        <a class="nav-link link-body-emphasis dropdown-toggle" role="button" data-bs-toggle="dropdown" aria-expanded="false">
            {{ currentLanguage.toLowerCase() }}
        </a>

        <!-- dropdown menu -->
        <ul class="dropdown-menu">
            <li v-for="language in languages" :key="language.value">
                <a
                    class="btn dropdown-item"
                    @click="changeLanguage(language.value)"
                    :aria-pressed="currentLanguage === language.value ? 'true' : 'false'"
                >
                    <span>{{ language.label }}</span>
                    <span v-if="currentLanguage === language.value" class="ms-3"><font-awesome-icon :icon="['fas', 'check']" /></span>
                </a>
            </li>
        </ul>
    </div>
</template>

<script>
import { ref, onMounted, watch } from 'vue';
import { useI18n } from 'vue-i18n';

export default {
    setup() {
        const { locale } = useI18n();
        const languages = [
            { value: 'en', label: 'English' },
            //{ value: 'pt', label: 'Portuguese' },
        ];
        const currentLanguage = ref(locale.value);

        const getStoredLanguage = () => localStorage.getItem('lang');
        const setStoredLanguage = (lang) => localStorage.setItem('lang', lang);

        const getPreferredLanguage = () => {
            const storedLanguage = getStoredLanguage();
            return storedLanguage ? storedLanguage : 'en';
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