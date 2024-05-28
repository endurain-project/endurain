<template>
    <div class="toast-container position-fixed bottom-0 end-0 p-3">
        <div ref="toastElement" class="toast align-items-center" role="alert" aria-live="assertive" aria-atomic="true">
            <div class="d-flex">
                <div class="toast-body text-primary-emphasis">
                    <span class="spinner-border spinner-border-sm me-2" aria-hidden="true"></span>
                    <font-awesome-icon :icon="['fas', 'fa-circle-exclamation']" />
                    <span class="ms-1">{{ loadingMessage }}</span>
                </div>
                <button type="button" class="btn-close btn-close-white me-2 m-auto" data-bs-dismiss="toast" aria-label="Close" v-if="closable"></button>
            </div>
        </div>
    </div>
</template>

<script>
    import { computed, onMounted, ref, watch } from 'vue';
    import { useLoadingAlertStore } from '@/stores/Alerts/loadingAlert';
    import BootstrapToast from 'bootstrap/js/dist/toast';

    export default {
        setup() {
            const loadingAlertStore = useLoadingAlertStore();
            const toastElement = ref(null);

            // Access both stats directly from the store
            const loadingMessage = computed(() => loadingAlertStore.message);
            const closable = computed(() => loadingAlertStore.closable);

            let toastInstance = null;

            // Initialize and show toast when component is mounted
            onMounted(() => {
                if (toastElement.value) {
                    toastInstance = new BootstrapToast(toastElement.value);
                    toastInstance.show();
                }
            });

            // Reactively show the toast when loadingMessage changes
            watch(loadingMessage, (newVal) => {
                if (newVal && toastInstance) {
                    toastInstance.show();
                }
            });

            return {
                toastElement,
                loadingMessage,
                closable,
            };
        },
    };
</script>