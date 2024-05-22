<script setup>
  import { RouterView } from 'vue-router'
  import NavbarComponent from './components/NavbarComponent.vue'
  import FooterComponent from './components/FooterComponent.vue'
</script>

<template>
  <NavbarComponent />
  <main class="container py-4 bg-body">
    <RouterView />
  </main>
  <FooterComponent />
</template>