<template>
    <div class="toast-container position-fixed top-0 start-50 translate-middle-x p-3">
        <div v-for="(toast, index) in toastStore.toasts" :key="index">
            <ToastComponent 
                :message="toast.message" 
                :type="toast.type" 
                :closable="toast.closable"
            />
        </div>
    </div>
</template>

<script>
import { useToastStore } from '@/stores/toastStore';
import ToastComponent from '@/components/Toasts/ToastComponent.vue';

export default {
    components: {
        ToastComponent,
    },
    setup() {
        const toastStore = useToastStore();

        return {
            toastStore,
        };
    },
};
</script>
