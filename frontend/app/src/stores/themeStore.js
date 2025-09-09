import { defineStore } from 'pinia'

export const useThemeStore = defineStore('theme', {
  state: () => ({
    theme: 'auto'
  }),
  actions: {
    setTheme(theme) {
      this.theme = theme
      localStorage.setItem('theme', theme)
    },
    loadThemeFromStorage() {
      const storedTheme = localStorage.getItem('theme')
      if (storedTheme) {
        this.theme = storedTheme
      } else {
        this.setTheme('auto')
      }
    }
  }
})
