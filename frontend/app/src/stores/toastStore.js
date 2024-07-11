import { defineStore } from 'pinia';

export const useToastStore = defineStore('toast', {
    state: () => ({
        toasts: [],
    }),
    actions: {
        addToast(toast) {
            this.toasts.push(toast);
        },
        removeToast(index) {
            this.toasts.splice(index, 1);
        },
    },
});
