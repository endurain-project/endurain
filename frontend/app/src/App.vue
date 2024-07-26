<script setup>
  import { RouterView } from 'vue-router'
  import ToastContainerComponent from './components/Toasts/ToastContainerComponent.vue'
  import NavbarComponent from './components/Navbar/NavbarComponent.vue'
  import FooterComponent from './components/FooterComponent.vue'
</script>

<template>
  <NavbarComponent />
  <ToastContainerComponent />
  <main class="container py-4 bg-body">
    <RouterView />
  </main>
  <FooterComponent />
</template>