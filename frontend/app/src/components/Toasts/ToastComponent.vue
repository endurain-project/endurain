<template>
    <div ref="toastElement" class="toast align-items-center mb-3" role="alert" aria-live="assertive" aria-atomic="true">
        <div class="d-flex">
            <div class="toast-body fs-6" :class="{ 'text-success-emphasis': type === 'success', 'text-danger-emphasis': type === 'danger', 'text-warning-emphasis': type === 'warning', 'text-primary-emphasis': type === 'loading'  }">
                <!-- success elements -->
                <font-awesome-icon :icon="['fas', 'circle-check']" v-if="type === 'success'"/>
                <!-- danger elements -->
                <font-awesome-icon :icon="['fas', 'fa-circle-exclamation']"  v-if="type === 'danger'"/>
                <!-- warning elements -->
                <font-awesome-icon :icon="['fas', 'fa-circle-exclamation']"  v-if="type === 'warning'"/>
                <!-- loading elements -->
                <span class="spinner-border spinner-border-sm me-2" aria-hidden="true" v-if="type === 'loading'"></span>
                <font-awesome-icon :icon="['fas', 'fa-circle-exclamation']"  v-if="type === 'loading'"/>
                <span class="ms-1">{{ message }}</span>
            </div>
            <button type="button" class="btn-close btn-close-white me-2 m-auto" data-bs-dismiss="toast" aria-label="Close" v-if="closable"></button>
        </div>
        <div class="progress" style="height: 3px;">
            <div class="progress-bar" :class="{ 'bg-success': type === 'success', 'bg-danger': type === 'danger', 'bg-warning': type === 'warning', 'bg-loading': type === 'loading'  }" role="progressbar" :style="{ width: `${progress}%` }"></div>
        </div>
    </div>
</template>

<script>
import { computed, onMounted, ref, watch } from 'vue';
import BootstrapToast from 'bootstrap/js/dist/toast';

export default {
    props: {
        type: {
            type: String,
            required: true,
        },
        message: {
            type: String,
            required: true,
        },
        closable: {
            type: Boolean,
            default: true,
        },
        duration: {
            type: Number,
            default: 5000, // default duration of the toast in milliseconds
        },
    },
    setup(props) {
        const toastElement = ref(null);
        let toastInstance = null;
        const type = computed(() => props.type);
        const message = ref(props.message);
        const closable = ref(props.closable);
        const progress = ref(100);

        const startProgress = () => {
            const intervalDuration = 100; // update progress every 100 ms
            const decrementAmount = (105 / props.duration) * intervalDuration;
            const interval = setInterval(() => {
                progress.value -= decrementAmount;
                if (progress.value <= 0) {
                    clearInterval(interval);
                }
            }, intervalDuration);
        };

        // Initialize and show toast when component is mounted
        onMounted(() => {
            if (toastElement.value) {
                toastInstance = new BootstrapToast(toastElement.value, { delay: props.duration });
                toastInstance.show();
                startProgress();
            }
        });

        // Reactively show the toast when message changes
        watch(message, (newVal) => {
            if (newVal && toastInstance) {
                toastInstance.show();
                startProgress();
            }
        });

        return {
            toastElement,
            type,
            message,
            closable,
            progress,
        }
    },
};
</script>