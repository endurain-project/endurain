<template>
  <div class="container-fluid py-4 route-detail-page" v-if="route">
    <div class="row mb-3">
      <div
        class="col-12 d-flex justify-content-between align-items-md-center flex-column flex-md-row gap-3"
      >
        <div>
          <h2 class="mb-1">{{ route.name }}</h2>
          <div class="d-flex gap-2 align-items-center text-muted flex-wrap">
            <span class="badge bg-secondary">{{ formatActivityType(route.activity_type) }}</span>
            <span v-if="route.sub_type" class="badge detail-subtype-badge">{{
              formatSubType(route.sub_type)
            }}</span>
            <span
              ><font-awesome-icon :icon="['far', 'calendar']" />
              {{ new Date(route.created_at).toLocaleDateString() }}</span
            >
          </div>
        </div>
        <div class="d-flex gap-2 flex-wrap">
          <button class="btn btn-outline-primary" @click="editRoute">
            <font-awesome-icon :icon="['fas', 'pen']" /> {{ $t('routesView.btn_edit') }}
          </button>
          <button class="btn btn-success" @click="downloadGpx" :disabled="isExporting">
            <font-awesome-icon
              :icon="['fas', isExporting ? 'spinner' : 'download']"
              :class="{ 'fa-spin': isExporting }"
            />
            {{ $t('routesView.btn_export_gpx') }}
          </button>
          <button class="btn btn-outline-danger" @click="deleteRoute" :disabled="isDeleting">
            <font-awesome-icon :icon="['fas', 'trash']" /> {{ $t('routesView.btn_delete') }}
          </button>
        </div>
      </div>
    </div>

    <div class="row mb-4 g-3">
      <div class="col-sm-6 col-md-4">
        <div class="card detail-surface-card border-0 h-100">
          <div class="card-body text-center p-3">
            <h6 class="detail-muted mb-1">{{ $t('routesView.cols_distance') }}</h6>
            <h4 class="mb-0">{{ (route.distance / 1000).toFixed(2) }} km</h4>
          </div>
        </div>
      </div>
      <div class="col-sm-6 col-md-4">
        <div class="card detail-surface-card border-0 h-100">
          <div class="card-body text-center p-3">
            <h6 class="detail-muted mb-1">{{ $t('routesView.ele_gain') }}</h6>
            <h4 class="mb-0">{{ route.elevation_gain || 0 }} m</h4>
          </div>
        </div>
      </div>
      <div class="col-sm-6 col-md-4">
        <div class="card detail-surface-card border-0 h-100">
          <div class="card-body text-center p-3">
            <h6 class="detail-muted mb-1">{{ $t('routesView.ele_loss') }}</h6>
            <h4 class="mb-0">{{ route.route_data?.elevation_loss || 0 }} m</h4>
          </div>
        </div>
      </div>
    </div>

    <div class="row mb-4">
      <div class="col-12">
        <div
          ref="mapContainerRef"
          class="w-100 rounded shadow-sm border"
          style="height: 50vh"
        ></div>
      </div>
    </div>

    <div class="row g-4">
      <div class="col-md-4">
        <div class="card detail-surface-card shadow-sm h-100 border-0">
          <div class="card-header detail-card-header">
            <h5 class="mb-0">{{ $t('routesView.form_desc') }}</h5>
          </div>
          <div class="card-body">
            <p v-if="route.description" class="mb-0">{{ route.description }}</p>
            <p v-else class="detail-muted fst-italic mb-0">{{ $t('routesView.no_desc') }}</p>
          </div>
        </div>
      </div>

      <div class="col-md-8">
        <div class="card detail-surface-card shadow-sm h-100 border-0">
          <div class="card-header detail-card-header">
            <h5 class="mb-0">{{ $t('routesView.waypoints') }}</h5>
          </div>
          <div class="card-body p-0">
            <div class="table-responsive" style="max-height: 380px">
              <table class="table detail-table table-hover mb-0 align-middle">
                <thead class="sticky-top detail-table-head">
                  <tr>
                    <th>#</th>
                    <th>{{ $t('routesView.city') }}</th>
                    <th>{{ $t('routesView.cols_coords') }}</th>
                    <th>{{ $t('routesView.form_type') }}</th>
                    <th>{{ $t('routesView.cols_distance') }}</th>
                    <th>{{ $t('routesView.cols_ele') }}</th>
                  </tr>
                </thead>
                <tbody>
                  <tr v-for="detail in waypointDetails" :key="detail.id">
                    <td>{{ detail.index + 1 }}</td>
                    <td>
                      <span v-if="detail.city">{{ detail.city }}</span>
                      <span v-else class="detail-muted">{{ detail.fallbackCity }}</span>
                    </td>
                    <td>
                      <small>{{ detail.lat.toFixed(5) }}, {{ detail.lng.toFixed(5) }}</small>
                    </td>
                    <td>
                      <span v-if="detail.index === 0" class="badge bg-success">{{
                        $t('routesView.start')
                      }}</span>
                      <span
                        v-else-if="detail.index === waypointDetails.length - 1"
                        class="badge bg-danger"
                        >{{ $t('routesView.finish') }}</span
                      >
                      <span v-else class="badge bg-secondary">{{ $t('routesView.step') }}</span>
                    </td>
                    <td>{{ formatCumulativeDistance(detail.cumulativeDistance) }}</td>
                    <td>{{ formatElevationDelta(detail.elevationDelta) }}</td>
                  </tr>
                </tbody>
              </table>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>

  <div v-else-if="isLoading" class="d-flex justify-content-center py-5">
    <div class="spinner-border text-primary" role="status"></div>
  </div>
</template>

<script setup lang="ts">
import { useI18n } from 'vue-i18n'
const { t } = useI18n()
import { ref, onMounted, onUnmounted, computed, useTemplateRef } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import L from 'leaflet'
import 'leaflet/dist/leaflet.css'
import { routesService } from '@/services/routesService'
import { push } from 'notivue'

interface Waypoint {
  lat: number
  lng: number
  segmentDistance?: number
  [key: string]: any
}

interface RouteData {
  coordinates: number[][]
  waypoints: Waypoint[]
  [key: string]: any
}

interface Route {
  id: number
  user_id: number
  name: string
  description: string
  activity_type: string
  sub_type: string
  distance: number
  elevation_gain: number
  route_data: RouteData
  created_at: string
  updated_at: string
}

interface GeocodeItem {
  key: string
  city: string
}

const routeParam = useRoute()
const router = useRouter()

const route = ref<Route | null>(null)
const isLoading = ref<boolean>(true)
const isDeleting = ref<boolean>(false)
const isExporting = ref<boolean>(false)
const waypointCities = ref<Record<number, string>>({})
const waypointElevations = ref<number[]>([])

const mapContainerRef = useTemplateRef<HTMLElement>('mapContainerRef')
let map: L.Map | null = null
let polyline: L.Polyline | null = null
let mapInitTimer: ReturnType<typeof setTimeout> | null = null

const waypointsList = computed(() => {
  if (!route.value?.route_data?.waypoints) {
    return []
  }

  return route.value.route_data.waypoints
})

const waypointDetails = computed(() => {
  let cumulativeDistance = 0

  return waypointsList.value.map((waypoint, index) => {
    const previousWaypoint = waypointsList.value[index - 1]
    const prevElevVal = waypointElevations.value[index - 1]
    const currElevVal = waypointElevations.value[index]
    const previousElevation: number | null = typeof prevElevVal === 'number' ? prevElevVal : null
    const currentElevation: number | null = typeof currElevVal === 'number' ? currElevVal : null
    const fallbackDistance = previousWaypoint
      ? L.latLng(previousWaypoint.lat, previousWaypoint.lng).distanceTo(
          L.latLng(waypoint.lat, waypoint.lng)
        )
      : null
    const segmentDistanceValue =
      index === 0
        ? 0
        : waypoint.segmentDistance !== undefined && Number.isFinite(waypoint.segmentDistance)
          ? waypoint.segmentDistance
          : fallbackDistance || 0

    cumulativeDistance += segmentDistanceValue || 0

    return {
      id: `${index}-${waypoint.lat}-${waypoint.lng}`,
      index,
      lat: waypoint.lat,
      lng: waypoint.lng,
      city: waypointCities.value[index] || '',
      fallbackCity: `${waypoint.lat.toFixed(3)}, ${waypoint.lng.toFixed(3)}`,
      cumulativeDistance,
      elevationDelta:
        previousElevation === null ||
        currentElevation === null ||
        !Number.isFinite(previousElevation) ||
        !Number.isFinite(currentElevation)
          ? null
          : currentElevation - previousElevation
    }
  })
})

const startIcon = L.divIcon({
  className: 'custom-div-icon',
  html: `<div style="background-color: green; width: 14px; height: 14px; border-radius: 50%; border: 2px solid white;"></div>`,
  iconSize: [14, 14],
  iconAnchor: [7, 7]
})

const endIcon = L.divIcon({
  className: 'custom-div-icon',
  html: `<div style="background-color: red; width: 14px; height: 14px; border-radius: 50%; border: 2px solid white;"></div>`,
  iconSize: [14, 14],
  iconAnchor: [7, 7]
})

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

const formatCumulativeDistance = (distance: number | null) => {
  if (distance === null || !Number.isFinite(distance)) {
    return '-'
  }

  return `${(distance / 1000).toFixed(2)} km`
}

const formatElevationDelta = (delta: number | null) => {
  if (delta === null || !Number.isFinite(delta)) {
    return '-'
  }

  const rounded = Math.round(delta)
  return `${rounded > 0 ? '+' : ''}${rounded} m`
}

const buildGpxFilename = (name: string) => {
  const safeName = (name || t('routesView.default_name'))
    .normalize('NFD')
    .replace(/[\u0300-\u036f]/g, '')
    .replace(/[^a-zA-Z0-9]+/g, '_')
    .replace(/^_+|_+$/g, '')
    .toLowerCase()

  return `${safeName || t('routesView.default_name')}.gpx`
}

const initMap = () => {
  if (!route.value?.route_data || !mapContainerRef.value) {
    return
  }

  if ((mapContainerRef.value as HTMLElement & { _leaflet_id?: number })._leaflet_id) {
    ;(L.DomUtil.get(mapContainerRef.value) as any)?._leaflet_map?.remove()
  }
  if (map) {
    map.remove()
    map = null
  }

  map = L.map(mapContainerRef.value)

  L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
    maxZoom: 19,
    attribution: '© OpenStreetMap contributors'
  }).addTo(map)

  const coordinates = route.value.route_data.coordinates || []
  if (coordinates.length > 0) {
    const latLngs = coordinates.map(
      (coordinate) => [coordinate[1], coordinate[0]] as [number, number]
    )
    polyline = L.polyline(latLngs, { color: 'blue', weight: 4 }).addTo(map)
    map.fitBounds(polyline.getBounds(), { padding: [20, 20] })
  }

  const waypoints = route.value.route_data?.waypoints || []
  if (waypoints.length > 0) {
    const firstWaypoint = waypoints[0]
    if (firstWaypoint) {
      L.marker([firstWaypoint.lat, firstWaypoint.lng], { icon: startIcon }).addTo(map)
    }

    if (waypoints.length > 1) {
      const lastWaypoint = waypoints[waypoints.length - 1]
      if (lastWaypoint) {
        L.marker([lastWaypoint.lat, lastWaypoint.lng], { icon: endIcon }).addTo(map)
      }
    }
  }
}

const fetchWaypointMetadata = async () => {
  if (waypointsList.value.length === 0) {
    waypointCities.value = {}
    waypointElevations.value = []
    return
  }

  try {
    const latitude = waypointsList.value.map((waypoint) => waypoint.lat.toFixed(6)).join(',')
    const longitude = waypointsList.value.map((waypoint) => waypoint.lng.toFixed(6)).join(',')
    const queryParams = new URLSearchParams({ latitude, longitude })
    const elevationResponse = await fetch(
      `https://api.open-meteo.com/v1/elevation?${queryParams.toString()}`
    )

    if (elevationResponse.ok) {
      const elevationData = await elevationResponse.json()
      waypointElevations.value = Array.isArray(elevationData?.elevation)
        ? elevationData.elevation
        : []
    }
  } catch (error) {
    console.error(error)
  }

  const nextCities: Record<number, string> = {}
  try {
    const response = await routesService.reverseGeocodeBatch(
      waypointsList.value.map((waypoint, index) => ({
        key: String(index),
        lat: waypoint.lat,
        lon: waypoint.lng
      }))
    )

    ;(response?.results || []).forEach((item: GeocodeItem) => {
      const index = Number(item.key)
      if (Number.isInteger(index)) {
        nextCities[index] = item.city
      }
    })
  } catch (error) {
    console.error(error)
  }

  waypointCities.value = nextCities
}

const loadRoute = async () => {
  try {
    const response = await routesService.getRoute(routeParam.params.id)
    route.value = response

    // Execute metadata fetch asynchronously to unblock map rendering
    fetchWaypointMetadata()

    mapInitTimer = setTimeout(() => {
      initMap()
    }, 100)
  } catch (error) {
    push.error(t('routesView.error_load_detail'))
    router.push({ name: 'routes-list' })
  } finally {
    isLoading.value = false
  }
}

const editRoute = () => {
  if (!route.value) return
  router.push({ name: 'route-edit', params: { id: route.value.id } })
}

const downloadGpx = async () => {
  if (!route.value) return
  isExporting.value = true
  try {
    const blob = await routesService.downloadRouteGpx(route.value.id)
    const blobUrl = window.URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = blobUrl
    link.download = buildGpxFilename(route.value.name)
    document.body.appendChild(link)
    link.click()
    link.remove()
    window.URL.revokeObjectURL(blobUrl)
  } catch (error) {
    console.error(error)
    push.error(t('routesView.error_export_gpx'))
  } finally {
    isExporting.value = false
  }
}

const deleteRoute = async () => {
  if (!route.value) return
  if (!confirm(t('routesView.confirm_delete'))) {
    return
  }

  isDeleting.value = true
  try {
    await routesService.deleteRoute(route.value.id)
    push.success(t('routesView.success_delete'))
    router.push({ name: 'routes-list' })
  } catch (error) {
    push.error(t('routesView.error_delete'))
    isDeleting.value = false
  }
}

onMounted(() => {
  loadRoute()
})

onUnmounted(() => {
  if (mapInitTimer) {
    clearTimeout(mapInitTimer)
    mapInitTimer = null
  }
  if (map) {
    map.remove()
    map = null
  }
})
</script>

<style scoped>
.detail-surface-card {
  background: #dfe3e7 !important;
  color: #1f2937;
}

.detail-card-header {
  background: rgba(223, 227, 231, 0.95) !important;
  border-bottom: 1px solid rgba(15, 23, 42, 0.08);
}

.detail-subtype-badge {
  background: rgba(33, 37, 41, 0.75);
  color: #ffffff;
}

.detail-table-head {
  background: #d4dbe2 !important;
}

.detail-table {
  color: inherit;
  --bs-table-bg: #dfe3e7;
  --bs-table-striped-bg: #d7dde4;
  --bs-table-hover-bg: #ccd4dc;
  --bs-table-color: #1f2937;
}

.detail-muted {
  color: #6c757d;
}

:global([data-bs-theme='dark']) .detail-surface-card {
  background: #2f353e !important;
  color: #edf2f7;
}

:global([data-bs-theme='dark']) .detail-card-header {
  background: rgba(57, 65, 76, 0.96) !important;
  border-bottom-color: rgba(255, 255, 255, 0.08);
  color: #edf2f7;
}

:global([data-bs-theme='dark']) .detail-table-head {
  background: #39414b !important;
  color: #edf2f7;
}

:global([data-bs-theme='dark']) .detail-table {
  --bs-table-bg: #2f353e;
  --bs-table-striped-bg: #353d47;
  --bs-table-hover-bg: #3b4450;
  --bs-table-color: #edf2f7;
}

:global([data-bs-theme='dark']) .route-detail-page .table-responsive {
  background: #2f353e !important;
}

:global([data-bs-theme='dark']) .detail-muted {
  color: #b6c1cd;
}

:global([data-bs-theme='dark']) .detail-subtype-badge {
  background: rgba(255, 255, 255, 0.16);
  color: #edf2f7;
}
</style>
