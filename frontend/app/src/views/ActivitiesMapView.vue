<template>
  <div class="activities-map-view">
    <h1>{{ $t('activitiesMapView.title') }}</h1>
    <!-- Activities map component -->
    <div class="map-container mt-4">
      <ActivitiesMapComponent :activities="[]" source="activity" />
    </div>
  </div>
</template>

<script setup>
import { useI18n } from 'vue-i18n'
import ActivitiesMapComponent from '@/components/Activities/ActivitiesMapComponent.vue'

const { t } = useI18n()
</script>

<style scoped>
.activities-map-view {
  padding: 20px;
  max-width: 1200px;
  margin: 0 auto;
}

.map-container {
  width: 100%;
}
</style>
