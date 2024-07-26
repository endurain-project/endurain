import { useToastStore } from '../stores/toastStore';

export function addToast(message, type, closable) {
    const toastStore = useToastStore();
    toastStore.addToast({
        message: message,
        type: type,
        closable: closable,
    });
}