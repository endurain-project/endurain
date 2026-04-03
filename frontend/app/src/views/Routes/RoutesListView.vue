<template>
  <div class="container-fluid py-4">
    <div class="row mb-4">
      <div class="col-12 d-flex justify-content-between align-items-center">
        <h2>{{ $t('routesView.title_routes') }}</h2>
        <router-link :to="{ name: 'route-create' }" class="btn btn-primary">
          <font-awesome-icon :icon="['fas', 'plus']" /> {{ $t('routesView.title_create') }}
        </router-link>
      </div>
    </div>

    <div v-if="isLoading" class="text-center py-5">
      <div class="spinner-border text-primary" role="status">
        <span class="visually-hidden">{{ $t('routesView.search_loading') }}</span>
      </div>
    </div>

    <div v-else-if="routes.length === 0" class="text-center py-5 text-muted">
      <h4>{{ $t('routesView.no_routes') }}</h4>
      <p>{{ $t('routesView.start_creating') }}</p>
    </div>

    <div v-else class="row row-cols-1 row-cols-md-2 row-cols-lg-3 g-4">
      <div class="col" v-for="route in routes" :key="route.id">
        <div 
          class="card h-100 shadow-sm route-card border-0" 
          @click="goToDetail(route.id)"
          @keydown.enter="goToDetail(route.id)"
          @keydown.space.prevent="goToDetail(route.id)"
          tabindex="0"
          role="button"
          :aria-label="route.name"
        >
          <div class="route-preview border-bottom position-relative">
            <div :id="`map-preview-${route.id}`" class="route-map-container"></div>
            <div
              class="route-preview-overlay position-absolute top-0 start-0 end-0 p-2 d-flex justify-content-between align-items-start"
            >
              <span class="badge" :class="getActivityBadgeClass(route.activity_type)">
                {{ formatActivityType(route.activity_type) }}
              </span>
              <span v-if="route.sub_type" class="badge route-subtype-badge">
                {{ formatSubType(route.sub_type) }}
              </span>
            </div>
          </div>
          <div class="card-body route-card-body">
            <h5 class="card-title text-truncate">{{ route.name }}</h5>
            <p class="card-text route-card-description small text-truncate">
              {{ route.description || $t('routesView.no_desc') }}
            </p>
          </div>
          <div class="card-footer route-card-footer d-flex justify-content-between small">
            <span
              ><font-awesome-icon :icon="['fas', 'ruler']" />
              {{ (route.distance / 1000).toFixed(2) }} km</span
            >
            <span v-if="route.elevation_gain"
              ><font-awesome-icon :icon="['fas', 'mountain']" /> {{ route.elevation_gain }} m</span
            >
            <span
              ><font-awesome-icon :icon="['far', 'calendar']" />
              {{ new Date(route.created_at).toLocaleDateString() }}</span
            >
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { useI18n } from 'vue-i18n'
const { t } = useI18n()
import { ref, onMounted, onUnmounted, nextTick } from 'vue'
import { useRouter } from 'vue-router'
import L from 'leaflet'
import 'leaflet/dist/leaflet.css'
import { routesService } from '@/services/routesService'
import { push } from 'notivue'

interface Route {
  id: number
  user_id: number
  name: string
  description?: string
  activity_type: string
  sub_type?: string
  distance: number
  elevation_gain: number
  created_at: string
  updated_at: string
  route_data: {
    coordinates: number[][]
    waypoints?: any[]
    [key: string]: any
  }
}

const router = useRouter()
const routes = ref<Route[]>([])
const isLoading = ref<boolean>(true)
const previewMaps = ref<Record<number, L.Map>>({})

const STROKE_COLORS: Record<string, string> = {
  cycling: '#0d6efd',
  running: '#198754',
  hiking: '#c57a00',
  other: '#6c757d'
}

const loadRoutes = async () => {
  try {
    const response = await routesService.getRoutes()
    routes.value = response || []
  } catch (error) {
    push.error(t('routesView.error_load'))
    console.error(error)
  } finally {
    isLoading.value = false
  }
  await nextTick()
  initPreviewMaps()
}

const initPreviewMaps = () => {
  routes.value.forEach((route) => {
    const el = document.getElementById(`map-preview-${route.id}`) as HTMLElement & {
      _leaflet_id?: number
    }
    if (!el || previewMaps.value[route.id] || el._leaflet_id) return

    const map = L.map(el, {
      zoomControl: false,
      dragging: false,
      scrollWheelZoom: false,
      doubleClickZoom: false,
      touchZoom: false,
      keyboard: false,
      attributionControl: false,
      boxZoom: false
    })

    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
      maxZoom: 18
    }).addTo(map)

    const coordinates = route.route_data?.coordinates || []
    const latLngs = coordinates
      .filter((c) => Array.isArray(c) && c.length >= 2)
      .map((c) => [c[1], c[0]] as [number, number])

    const color = STROKE_COLORS[route.activity_type] || '#6c757d'
    if (latLngs.length >= 2) {
      const polyline = L.polyline(latLngs, { color, weight: 4, opacity: 0.9 }).addTo(map)
      map.fitBounds(polyline.getBounds(), { padding: [10, 10] })
    } else {
      map.setView([46.2, 2.3], 5)
    }

    previewMaps.value[route.id] = map
  })
}

const goToDetail = (id: number) => {
  router.push({ name: 'route-detail', params: { id } })
}

const getActivityBadgeClass = (type: string) => {
  if (type === 'cycling') return 'bg-info text-dark'
  if (type === 'running') return 'bg-success'
  if (type === 'other') return 'bg-secondary'
  return 'bg-primary'
}

const formatActivityType = (type: string) => {
  const map: Record<string, string> = {
    cycling: t('routesView.type_cycling'),
    running: t('routesView.type_running'),
    hiking: t('routesView.type_hiking'),
    other: t('routesView.type_other')
  }
  return map[type] || type
}

const formatSubType = (type: string) => {
  const map: Record<string, string> = {
    road: t('routesView.subtype_road'),
    gravel: t('routesView.subtype_gravel'),
    mountain_bike: t('routesView.subtype_mountain_bike'),
    bikepacking: t('routesView.subtype_bikepacking'),
    road_running: t('routesView.subtype_road_running'),
    trail_running: t('routesView.subtype_trail_running'),
    interval: t('routesView.subtype_interval'),
    long_run: t('routesView.subtype_long_run'),
    day_hike: t('routesView.subtype_day_hike'),
    trekking: t('routesView.subtype_trekking'),
    fast_hiking: t('routesView.subtype_fast_hiking'),
    nordic_walking: t('routesView.subtype_nordic_walking'),
    trail: t('routesView.subtype_trail'),
    other: t('routesView.type_other')
  }
  return map[type] || type
}

onMounted(() => {
  loadRoutes()
})

onUnmounted(() => {
  Object.values(previewMaps.value).forEach((map) => map.remove())
  previewMaps.value = {}
})
</script>

<style scoped>
.route-card {
  cursor: pointer;
  transition:
    transform 0.2s,
    box-shadow 0.2s;
  background: #f6f7f9;
  color: #1f2937;
}
.route-card:hover {
  transform: translateY(-5px);
  box-shadow: 0 10px 20px rgba(0, 0, 0, 0.1) !important;
}
.route-preview {
  height: 150px;
  overflow: hidden;
}
.route-map-container {
  width: 100%;
  height: 150px;
  pointer-events: none;
}
.route-preview-overlay {
  pointer-events: none;
}
.route-subtype-badge {
  background: rgba(33, 37, 41, 0.75);
  color: #ffffff;
}
.route-card-description {
  color: #6c757d;
}
.route-card-footer {
  background: rgba(246, 247, 249, 0.9);
  color: #6c757d;
}
:global([data-bs-theme='dark']) .route-card {
  background: #252b33;
  color: #edf2f7;
}
:global([data-bs-theme='dark']) .route-card-footer {
  background: rgba(49, 57, 67, 0.9);
  color: #c6d0db;
}
:global([data-bs-theme='dark']) .route-card-description {
  color: #b5bfca;
}
:global([data-bs-theme='dark']) .route-subtype-badge {
  background: rgba(255, 255, 255, 0.16);
  color: #edf2f7;
}
</style>
