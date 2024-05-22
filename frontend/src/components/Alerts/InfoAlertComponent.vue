<template>
    <div class="alert alert-warning alert-dismissible d-flex align-items-center" role="alert">
        <font-awesome-icon :icon="['fas', 'fa-triangle-exclamation']" />
        <div class="ms-1">
            <span>{{ errorMessage }}</span>
            <button type="button" class="btn-close" data-bs-dismiss="alert" aria-label="Close" v-if="closable"></button>
        </div>
    </div>
</template>

<script>
import { computed } from 'vue';
import { useInfoAlertStore } from '@/stores/Alerts/infoAlert';

export default {
  setup() {
    const infoAlertStore = useInfoAlertStore();

    // Access both stats directly from the store
    const errorMessage = computed(() => infoAlertStore.message);
    const closable = computed(() => infoAlertStore.closable);

    return {
        errorMessage,
        closable,
    };
  },
};
</script>