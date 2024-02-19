import { defineStore } from 'pinia';

export const useErrorAlertStore = defineStore('errorAlert', {
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