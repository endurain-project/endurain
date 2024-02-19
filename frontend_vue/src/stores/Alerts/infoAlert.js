import { defineStore } from 'pinia';

export const useInfoAlertStore = defineStore('infoAlert', {
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