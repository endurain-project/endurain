<template>
    <form>
        <label for="themeSelect" class="form-label">Theme</label>
        <select class="form-select" id="themeSelect" aria-label="Select for theme picker">
            <option v-for="theme in themes" :key="theme.value" :value="theme.value" :selected="themeStore.theme == theme.value" @click="changeTheme(theme.value)">{{ theme.label }}</option>
        </select>
    </form>
</template>

<script>
import { onMounted } from 'vue';

import { useThemeStore } from '@/stores/themeStore';

export default {
    setup() {
        const themeStore = useThemeStore();
        const themes = [
            { value: 'light', label: 'Light' },
            { value: 'dark', label: 'Dark' },
            { value: 'auto', label: 'Auto' },
        ];

        const setTheme = (theme) => {
            if (theme === 'auto') {
                document.documentElement.setAttribute(
                    'data-bs-theme',
                    window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light'
                );
            } else {
                document.documentElement.setAttribute('data-bs-theme', theme);
            }
        };

        const changeTheme = (theme) => {
            setTheme(theme);
            themeStore.setTheme(theme);
        };

        onMounted(() => {
            setTheme(themeStore.theme);
        
            window.matchMedia('(prefers-color-scheme: dark)').addEventListener('change', () => {
                if (themeStore.theme !== 'light' && themeStore.theme !== 'dark') {
                    const preferredTheme = window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';

                    document.documentElement.setAttribute('data-bs-theme', preferredTheme);
                }
            });
        });

        return {
            themeStore,
            themes,
            changeTheme,
        };
    },
};
</script>