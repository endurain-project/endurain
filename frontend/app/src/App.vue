<script setup>
  import { RouterView } from 'vue-router'
  import NavbarComponent from './components/Navbar/NavbarComponent.vue'
  import FooterComponent from './components/FooterComponent.vue'
  import { Notivue, Notification, NotificationProgress, pastelTheme } from 'notivue'
</script>

<template>
  <Notivue v-slot="item">
    <Notification :item="item" :theme="pastelTheme">
      <NotificationProgress :item="item" />
    </Notification>
  </Notivue>
  <NavbarComponent />
  <main class="container py-4 bg-body">
    <RouterView />
  </main>
  <FooterComponent />
</template>