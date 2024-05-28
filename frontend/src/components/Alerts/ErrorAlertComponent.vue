<template>
    <div class="alert alert-danger alert-dismissible d-flex align-items-center" role="alert">
      <font-awesome-icon :icon="['fas', 'fa-circle-exclamation']" />
      <div class="ms-1">
        <span>{{ errorMessage }}</span>
        <button type="button" class="btn-close" data-bs-dismiss="alert" aria-label="Close" v-if="closable"></button>
      </div>
    </div>
</template>

<script>
import { computed } from 'vue';
import { useErrorAlertStore } from '@/stores/Alerts/errorAlert';

export default {
  setup() {
    const errorAlertStore = useErrorAlertStore();

    // Access both stats directly from the store
    const errorMessage = computed(() => errorAlertStore.message);
    const closable = computed(() => errorAlertStore.closable);

    return {
        errorMessage,
        closable,
    };
  },
};
</script>