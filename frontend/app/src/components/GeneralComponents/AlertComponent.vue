<template>
  <div class="alert alert-dismissible fade show" :class="`alert-${type}`" role="alert">
    <font-awesome-icon :icon="['fas', `${symbol}`]" class="me-1" />
    {{ message }}
    <button
      type="button"
      class="btn-close"
      data-bs-dismiss="alert"
      aria-label="Close"
      v-if="dismissible"
    ></button>
  </div>
</template>

<script setup>
const props = defineProps({
  message: {
    type: String,
    required: true
  },
  type: {
    type: String,
    default: 'info'
  },
  symbol: {
    type: String,
    default: 'circle-info'
  },
  dismissible: {
    type: Boolean,
    default: false
  }
})
</script>
