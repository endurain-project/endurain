<template>
  <div class="activities-map-component">
    <!-- Map container -->
    <div ref="activitiesMap" class="activities-map rounded" :style="mapStyle"></div>
    
    <!-- Loading state -->
    <div v-if="isLoading" class="map-loading-overlay">
      <LoadingComponent />
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import LoadingComponent from '@/components/GeneralComponents/LoadingComponent.vue'

const props = defineProps({
  activities: {
    type: Array,
    default: () => []
  },
  height: {
    type: String,
    default: '600px'
  }
})

const activitiesMap = ref(null)
const isLoading = ref(false)

// Computed properties
const mapStyle = computed(() => ({
  height: props.height,
  backgroundColor: '#e9ecef',
  // Always show grid background for map area
  backgroundImage: 
    'linear-gradient(45deg, #e9ecef 25%, transparent 25%),' +
    'linear-gradient(-45deg, #e9ecef 25%, transparent 25%),' +
    'linear-gradient(45deg, transparent 75%, #e9ecef 75%),' +
    'linear-gradient(-45deg, transparent 75%, #e9ecef 75%)',
  backgroundSize: '20px 20px',
  backgroundPosition: '0 0, 0 10px, 10px -10px, -10px 0px'
}))

// Lifecycle hooks
onMounted(() => {
  // Initialize map logic will go here
  console.log('ActivitiesMapComponent mounted with', props.activities.length, 'activities')
})
</script>

<style scoped>
.activities-map-component {
  position: relative;
  width: 100%;
}

.activities-map {
  width: 100%;
  position: relative;
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
  background-color: rgba(255, 255, 255, 0.7);
  z-index: 10;
}

.map-empty-state {
  position: absolute;
  top: 50%;
  left: 50%;
  transform: translate(-50%, -50%);
  text-align: center;
  color: #6c757d;
  z-index: 5;
}
</style>