import { defineStore } from 'pinia';

export const useLoadingAlertStore = defineStore('loadingAlert', {
    state: () => ({
        message: null,
        closable: false,
    }),
    actions: {
        setAlertMessage(message) {
            this.message = message;
        },
        setClosableState(closable) {
            this.closable = closable;
        }
    }
});