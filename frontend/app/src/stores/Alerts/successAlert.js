import { defineStore } from 'pinia';

export const useSuccessAlertStore = defineStore('successAlert', {
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