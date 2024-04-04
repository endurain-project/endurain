<template>
    <div class="toast-container position-fixed bottom-0 end-0 p-3">
        <div ref="toastElement" class="toast align-items-center" role="alert" aria-live="assertive" aria-atomic="true">
            <div class="d-flex">
                <div class="toast-body text-danger-emphasis">
                    <font-awesome-icon :icon="['fas', 'fa-circle-exclamation']" />
                    <span class="ms-1">{{ errorMessage }}</span>
                </div>
                <button type="button" class="btn-close btn-close-white me-2 m-auto" data-bs-dismiss="toast" aria-label="Close" v-if="closable"></button>
            </div>
        </div>
    </div>
</template>

<script>
    import { computed, onMounted, ref, watch } from 'vue';
    import { useErrorAlertStore } from '@/stores/Alerts/errorAlert';
    import BootstrapToast from 'bootstrap/js/dist/toast';

    export default {
        setup() {
            const errorAlertStore = useErrorAlertStore();
            const toastElement = ref(null);

            // Access both stats directly from the store
            const errorMessage = computed(() => errorAlertStore.message);
            const closable = computed(() => errorAlertStore.closable);

            let toastInstance = null;

            // Initialize and show toast when component is mounted
            onMounted(() => {
                if (toastElement.value) {
                    toastInstance = new BootstrapToast(toastElement.value);
                    toastInstance.show();
                }
            });

            // Reactively show the toast when errorMessage changes
            watch(errorMessage, (newVal) => {
                if (newVal && toastInstance) {
                    toastInstance.show();
                }
            });

            return {
                toastElement,
                errorMessage,
                closable,
            };
        },
    };
</script>