<script setup>
  import { RouterView } from 'vue-router'
  import NavbarComponent from './components/NavbarComponent.vue'
  import FooterComponent from './components/FooterComponent.vue'
</script>

<template>
  <NavbarComponent />
  <main class="container mt-4 mb-4">
    <RouterView />
  </main>
  <FooterComponent />
</template>