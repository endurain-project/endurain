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
import { ref, computed, onMounted, onUnmounted, nextTick, watch } from 'vue'
import LoadingComponent from '@/components/GeneralComponents/LoadingComponent.vue'
import L from 'leaflet'
import 'leaflet/dist/leaflet.css'
import { useServerSettingsStore } from '@/stores/serverSettingsStore'
import { activities } from '@/services/activitiesService'
import { activityStreams } from '@/services/activityStreams'
import { useAuthStore } from '@/stores/authStore'

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
const authStore = useAuthStore()
const activityTracks = ref([])
const color = '#2563eb'

// Computed map height based on source
const mapHeight = computed(() => props.source === 'home' ? '300px' : '500px')

// Computed properties
const mapStyle = computed(() => ({
  height: mapHeight.value
}))

// Fetch activities and their streams if not provided
const fetchActivities = async () => {
  if (props.activities.length > 0) {
    activityTracks.value = props.activities
    await fetchActivityStreams()
    return
  }

  try {
    isLoading.value = true
    if (authStore.isAuthenticated && authStore.user.id) {
      // Fetch activities for the current week (week 0)
      const response = await activities.getUserWeekActivities(authStore.user.id, 0)
      if (response) {
        activityTracks.value = response
        await fetchActivityStreams()
      }
    }
  } catch (error) {
    console.error('Error fetching activities:', error)
  } finally {
    isLoading.value = false
  }
}

// Fetch stream data for all activities
const fetchActivityStreams = async () => {
  if (!activityTracks.value || activityTracks.value.length === 0) return

  try {
    const streamPromises = activityTracks.value.map(async (activity) => {
      try {
        let streamData = null
        if (authStore.isAuthenticated) {
          const response = await activityStreams.getActivitySteamByStreamTypeByActivityId(
            activity.id, 7
          )
          console.log("response")
          console.log(response)
          streamData = response
        } else {
          const response = await activityStreams.getPublicActivitySteamByStreamTypeByActivityId(
            activity.id, 7
          )
          streamData = response?.data || null
        }
        
        // Only include activities with valid stream data
        if (streamData) {
          return { ...activity, activity_streams: [streamData] }
        } else {
          return null
        }
      } catch (error) {
        console.error(`Error fetching stream for activity ${activity.id}:`, error)
        return null
      }
    })

    const results = await Promise.all(streamPromises)
    // Filter out null results (activities without valid stream data)
    activityTracks.value = results.filter(result => result !== null)
  } catch (error) {
    console.error('Error fetching activity streams:', error)
  }
}

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

  // Add activity tracks to the map
  addActivityTracksToMap()
}

// Add activity tracks to the map
const addActivityTracksToMap = () => {
  if (!leafletMap.value || activityTracks.value.length === 0) {
    isLoading.value = false
    return
  }

  const bounds = []
  
  activityTracks.value.forEach((activity, index) => {
    try {
      if (activity.activity_streams && activity.activity_streams.length > 0) {
        // The stream data might be directly in activity_streams[0] or nested
        let streamData = activity.activity_streams[0]
        
        // Handle different possible structures
        if (streamData && streamData.data) {
          // If stream data is nested in a response object
          streamData = streamData.data
        }
        
        // Check if the stream data has the expected structure
        if (streamData && streamData.stream_waypoints && streamData.stream_waypoints.length > 0) {
          const validWaypoints = streamData.stream_waypoints.filter(
            (waypoint) => waypoint.lat && waypoint.lon
          )
          
          if (validWaypoints.length > 0) {
            const latlngs = validWaypoints.map((waypoint) => [waypoint.lat, waypoint.lon])
            
            const polyline = L.polyline(latlngs, {
              color: color,
              weight: 4,
              opacity: 0.8,
              lineJoin: 'round',
              lineCap: 'round'
            }).addTo(leafletMap.value)
            
            // Add bounds for fitting
            bounds.push(...latlngs)
          }
        }
      }
    } catch (error) {
      console.error(`Error processing activity ${activity.id}:`, error)
    }
  })
  
  // Fit map to all bounds
  if (bounds.length > 0) {
    leafletMap.value.fitBounds(bounds)
  } else {
    // If no bounds, fit to world view
    leafletMap.value.fitWorld()
  }
  
  isLoading.value = false
}

// Lifecycle hooks
onMounted(async () => {
  await fetchActivities()
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

// Watch for changes in activities prop
watch(
  () => props.activities,
  async (newActivities) => {
    if (newActivities && newActivities.length > 0) {
      activityTracks.value = newActivities
      if (leafletMap.value) {
        // Clear existing layers
        leafletMap.value.eachLayer(layer => {
          if (layer instanceof L.Polyline || layer instanceof L.Marker) {
            leafletMap.value.removeLayer(layer)
          }
        })
        addActivityTracksToMap()
      }
    }
  },
  { deep: true }
)
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
