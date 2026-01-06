<template>
  <footer :class="{ 'py-5 bg-body-tertiary': enableBackground }">
    <div class="container">
      <p class="text-center text-muted">
        {{ new Date().getFullYear() === 2023 ? '2023' : '2023 - ' + new Date().getFullYear() }}
        Endurain&reg; •
        <a class="link-body-emphasis" href="https://github.com/endurain-project" role="button"><font-awesome-icon
            :icon="['fab', 'fa-github']" /></a>
        •
        <a class="link-body-emphasis" href="https://docs.endurain.com"><font-awesome-icon :icon="['fas', 'book']" /></a>
        •
        <a class="link-body-emphasis" href="https://fosstodon.org/@endurain"><font-awesome-icon
            :icon="['fab', 'fa-mastodon']" /></a>
        •
        <a class="link-body-emphasis" href="https://discord.gg/6VUjUq2uZR"><font-awesome-icon
            :icon="['fab', 'fa-discord']" /></a>
        • v0.16.5
      </p>
      <p class="text-center text-muted">
        <img :src="INTEGRATION_LOGOS.strava" alt="Compatible with STRAVA image" height="25" />
        •
        <img class="ms-2" :src="INTEGRATION_LOGOS.garminConnectBadge" alt="Works with Garmin Connect image"
          height="25" />
      </p>
    </div>
  </footer>
</template>

<script setup>
import { INTEGRATION_LOGOS } from '@/constants/integrationLogoConstants'

defineProps({
  enableBackground: {
    type: Boolean,
    default: true
  }
})
</script>
