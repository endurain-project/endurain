<template>
    <div class="alert alert-primary d-flex align-items-center" role="alert">
      <div class="spinner-border" role="status">
        <span class="visually-hidden">Loading...</span>
      </div>
      <div class="ms-1">
        <span>{{ loadingMessage }}</span>
      </div>
    </div>
</template>

<script>
import { useLoadingAlertStore } from '@/stores/Alerts/errorAlert';

export default {
  setup() {
    const loadingAlertStore = useLoadingAlertStore();

    // Access both stats directly from the store
    const loadingMessage = computed(() => loadingAlertStore.message);

    return {
        loadingMessage,
    };
  },
};
</script>