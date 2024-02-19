<template>
    <div class="alert alert-success alert-dismissible d-flex align-items-center" role="alert">
      <font-awesome-icon :icon="['fas', 'circle-check']" />
      <div class="ms-1">
        <span>{{ errorMessage }}</span>
        <button type="button" class="btn-close" data-bs-dismiss="alert" aria-label="Close" v-if="closable"></button>
      </div>
    </div>
</template>

<script>
import { computed } from 'vue';
import { useSuccessAlertStore } from '@/stores/Alerts/successAlert';

export default {
  setup() {
    const successAlertStore = useSuccessAlertStore();

    // Access both stats directly from the store
    const errorMessage = computed(() => successAlertStore.message);
    const closable = computed(() => successAlertStore.closable);

    return {
        errorMessage,
        closable,
    };
  },
};
</script>