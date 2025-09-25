<template>
  <div class="card shadow-sm h-100 bg-primary-subtle text-primary-emphasis">
    <div class="card-body d-flex flex-column justify-content-center">
      <h6 class="card-subtitle mb-2">{{ title }}</h6>
      <p class="card-text h4">{{ subTitle }}</p>
    </div>
  </div>
</template>

<script>
export default {
  props: {
    title: {
      type: String,
      required: true
    },
    subTitle: {
      type: String,
      required: true
    }
  }
}
</script>
