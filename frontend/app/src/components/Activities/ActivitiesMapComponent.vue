<template>
  <div class="activities-map-component">
    <!-- Map container -->
    <div ref="activitiesMap" class="map rounded w-100" :style="mapStyle"></div>
    
    <!-- Loading state -->
    <div v-if="isLoading" class="map-loading-overlay">
      <LoadingComponent />
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted, nextTick } from 'vue'
import LoadingComponent from '@/components/GeneralComponents/LoadingComponent.vue'
import L from 'leaflet'
import 'leaflet/dist/leaflet.css'
import { useServerSettingsStore } from '@/stores/serverSettingsStore'

const props = defineProps({
  activities: {
    type: Array,
    default: () => []
  },
  source: {
    type: String,
    default: 'activity',
    validator: (value) => ['home', 'activity'].includes(value)
  }
})

const activitiesMap = ref(null)
const leafletMap = ref(null)
const isLoading = ref(true)
const serverSettingsStore = useServerSettingsStore()

// Computed map height based on source
const mapHeight = computed(() => props.source === 'home' ? '300px' : '500px')

// Computed properties
const mapStyle = computed(() => ({
  height: mapHeight.value
}))

// Initialize Leaflet map
const initMap = () => {
  if (!activitiesMap.value) return

  // Destroy previous map instance if exists
  if (leafletMap.value) {
    leafletMap.value.remove()
    leafletMap.value = null
  }

  leafletMap.value = L.map(activitiesMap.value, {
    dragging: true,
    touchZoom: true,
    scrollWheelZoom: true,
    zoomControl: true
  }).fitWorld()

  leafletMap.value.getContainer().style.backgroundColor =
    serverSettingsStore.serverSettings.map_background_color

  L.tileLayer(serverSettingsStore.serverSettings.tileserver_url, {
    attribution: serverSettingsStore.serverSettings.tileserver_attribution
  }).addTo(leafletMap.value)

  isLoading.value = false
}

// Lifecycle hooks
onMounted(() => {
  nextTick(() => {
    initMap()
  })
})

onUnmounted(() => {
  if (leafletMap.value) {
    leafletMap.value.remove()
    leafletMap.value = null
  }
})
</script>

<style scoped>
.activities-map-component {
  position: relative;
  width: 100%;
}

.map-loading-overlay {
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  display: flex;
  justify-content: center;
  align-items: center;
  background-color: rgba(255, 255, 255, 0.8);
  z-index: 10;
}

/* Leaflet map container needs proper sizing */
.activities-map-component :deep(.leaflet-container) {
  width: 100%;
  height: 100%;
}
</style>
