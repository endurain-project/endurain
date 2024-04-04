<template>    
    <!--<div class="toast-container position-fixed bottom-0 end-0 p-3">
        <div ref="toastElement" class="toast align-items-center" role="alert" aria-live="assertive" aria-atomic="true">
            <div class="toast-header text-success-emphasis">
                <font-awesome-icon :icon="['fas', 'circle-check']" />
                <strong class="ms-1 me-auto">Success</strong>
                <button type="button" class="btn-close btn-close-white me-2 m-auto" data-bs-dismiss="toast" aria-label="Close" v-if="closable"></button>
            </div>
            <div class="toast-body text-success-emphasis">
                <span>{{ successMessage }}</span>
            </div>
        </div>
    </div>-->
    <div class="toast-container position-fixed bottom-0 end-0 p-3">
        <div ref="toastElement" class="toast align-items-center" role="alert" aria-live="assertive" aria-atomic="true">
            <div class="d-flex">
                <div class="toast-body text-success-emphasis">
                    <font-awesome-icon :icon="['fas', 'circle-check']" />
                    <span class="ms-1">{{ successMessage }}</span>
                </div>
                <button type="button" class="btn-close btn-close-white me-2 m-auto" data-bs-dismiss="toast" aria-label="Close" v-if="closable"></button>
            </div>
        </div>
    </div>
</template>

<script>
    import { computed, onMounted, ref, watch } from 'vue';
    import { useSuccessAlertStore } from '@/stores/Alerts/successAlert';
    import BootstrapToast from 'bootstrap/js/dist/toast';

    export default {
        setup() {
            const successAlertStore = useSuccessAlertStore();
            const toastElement = ref(null);

            // Access both stats directly from the store
            const successMessage = computed(() => successAlertStore.message);
            const closable = computed(() => successAlertStore.closable);

            let toastInstance = null;

            // Initialize and show toast when component is mounted
            onMounted(() => {
                if (toastElement.value) {
                    toastInstance = new BootstrapToast(toastElement.value);
                    toastInstance.show();
                }
            });

            // Reactively show the toast when successMessage changes
            watch(successMessage, (newVal) => {
                if (newVal && toastInstance) {
                    toastInstance.show();
                }
            });

            return {
                toastElement,
                successMessage,
                closable,
            };
        },
    };
</script>