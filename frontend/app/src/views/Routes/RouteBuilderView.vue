<template>
  <div class="container-fluid py-3 h-100 d-flex flex-column">
    <div class="row mb-3">
      <div class="col-12 d-flex justify-content-between align-items-center">
        <h2>{{ pageTitle }}</h2>
        <div>
          <button
            class="btn btn-outline-primary me-2"
            @click="closeLoop"
            :disabled="waypoints.length < 2 || isLoopClosed"
          >
            <font-awesome-icon :icon="['fas', 'arrows-spin']" /> {{ $t('routesView.btn_loop') }}
          </button>
          <button class="btn btn-outline-secondary me-2" @click="undo" :disabled="!canUndo">
            <font-awesome-icon :icon="['fas', 'undo']" /> {{ $t('routesView.btn_undo') }}
          </button>
          <button class="btn btn-outline-secondary me-3" @click="redo" :disabled="!canRedo">
            <font-awesome-icon :icon="['fas', 'redo']" /> {{ $t('routesView.btn_redo') }}
          </button>
          <button class="btn btn-primary" @click="showSaveModal = true" :disabled="waypoints.length < 2">
            <font-awesome-icon :icon="['fas', 'save']" /> {{ isEditMode ? t('routesView.btn_save_edit') : t('routesView.btn_save') }}
          </button>
        </div>
      </div>
    </div>

    <div class="row flex-grow-1" style="min-height: 60vh;">
      <div class="col-12 h-100 position-relative d-flex flex-column">
        
        <div class="mb-2 d-flex">
          <div class="route-search position-relative w-100">
            <div class="input-group shadow-sm">
              <input
                id="route-location-search"
                type="text"
                class="form-control"
                :placeholder="$t('routesView.search_placeholder')"
                v-model="searchQuery"
                @input="handleSearchInput"
                @focus="handleSearchFocus"
                @blur="scheduleHideSearchSuggestions"
                @keyup.enter="searchLocation"
                :aria-label="$t('routesView.search_input_aria')"
                aria-autocomplete="list"
                :aria-expanded="showSearchSuggestions"
                aria-controls="route-search-suggestions"
              >
              <button class="btn btn-primary" type="button" @click="searchLocation" :disabled="isSearching" :aria-label="$t('routesView.search_button_aria')">
                <font-awesome-icon :icon="['fas', isSearching ? 'spinner' : 'search']" :class="{'fa-spin': isSearching}" />
              </button>
            </div>
            <div
              v-if="showSearchSuggestions && (searchSuggestions.length > 0 || isSearching)"
              id="route-search-suggestions"
              class="list-group route-search-dropdown shadow-sm"
              role="listbox"
            >
              <div v-if="isSearching && searchSuggestions.length === 0" class="list-group-item text-muted small">
                {{ $t('routesView.search_loading') }}
              </div>
              <button
                v-for="suggestion in searchSuggestions"
                :key="suggestion.id"
                type="button"
                class="list-group-item list-group-item-action"
                @mousedown.prevent="selectSearchSuggestion(suggestion)"
              >
                <div class="fw-semibold text-truncate">{{ suggestion.label }}</div>
                <div class="small text-body-secondary text-truncate">{{ suggestion.meta }}</div>
              </button>
            </div>
          </div>
        </div>

        <div class="flex-grow-1 position-relative">
          <div id="route-map" class="h-100 w-100 rounded shadow border"></div>
          
          <div v-show="isCalculating" class="loading-bar rounded-bottom text-center align-content-center" style="pointer-events:none;"></div>

        
        <div class="position-absolute bottom-0 start-50 translate-middle-x mb-3 bg-white p-2 rounded shadow-sm d-flex gap-3" style="z-index: 1000;">
          <div class="form-check form-switch d-flex align-items-center mb-0 text-dark">
            <input class="form-check-input me-2 mt-0" type="checkbox" role="switch" id="autoRouting" v-model="autoRouting">
            <label class="form-check-label mb-0" for="autoRouting">
              {{ $t('routesView.mode_auto') }}
            </label>
          </div>
          <div class="border-start border-secondary ps-3">
            <span class="text-dark fw-bold">{{ distanceLabel }} km</span>
          </div>
          <div class="border-start border-secondary ps-3">
            <span class="text-dark fw-bold">+{{ elevationGain }} m</span>
          </div>
          <div class="border-start border-secondary ps-3">
            <span class="text-dark fw-bold">-{{ elevationLoss }} m</span>
          </div>
          <div v-if="autoRouting" class="border-start border-secondary ps-3 d-flex align-items-center gap-1">
            <button
              class="btn btn-sm py-0 px-2"
              :class="routingMode === 'hybrid' ? 'btn-primary' : 'btn-outline-secondary'"
              @click="setRoutingMode('hybrid')"
              :title="t('routesView.mode_hybrid')"
            >
              <font-awesome-icon :icon="['fas', 'route']" />
            </button>
            <button
              class="btn btn-sm py-0 px-2"
              :class="routingMode === 'road' ? 'btn-primary' : 'btn-outline-secondary'"
              @click="setRoutingMode('road')"
              :title="t('routesView.mode_road')"
            >
              <font-awesome-icon :icon="['fas', 'road']" />
            </button>
            <button
              class="btn btn-sm py-0 px-2"
              :class="routingMode === 'path' ? 'btn-primary' : 'btn-outline-secondary'"
              @click="setRoutingMode('path')"
              :title="t('routesView.mode_path')"
            >
              <font-awesome-icon :icon="['fas', 'hiking']" />
            </button>
          </div>
        </div>
        </div>
      </div>
    </div>

    
    <div v-if="showSaveModal" class="modal fade show d-block" tabindex="-1" style="background: rgba(0,0,0,0.5)">
      <div class="modal-dialog modal-dialog-centered">
        <div class="modal-content">
          <div class="modal-header">
            <h5 class="modal-title">{{ isEditMode ? $t('routesView.title_edit') : $t('routesView.title_create') }}</h5>
            <button type="button" class="btn-close" @click="showSaveModal = false"></button>
          </div>
          <div class="modal-body">
            <div class="mb-3">
              <label for="routeName" class="form-label">{{ $t('routesView.form_name') }} <span class="text-danger">*</span></label>
              <input type="text" class="form-control" id="routeName" v-model="routeForm.name" required>
            </div>
            <div class="mb-3">
              <label for="routeType" class="form-label">{{ $t('routesView.form_type') }} <span class="text-danger">*</span></label>
              <select class="form-select" id="routeType" v-model="routeForm.activity_type">
                <option value="cycling">{{ $t('routesView.type_cycling') }}</option>
                <option value="running">{{ $t('routesView.type_running') }}</option>
                <option value="hiking">{{ $t('routesView.type_hiking') }}</option>
                <option value="other">{{ $t('routesView.type_other') }}</option>
              </select>
            </div>
            <div class="mb-3">
              <label for="routeSubType" class="form-label">{{ $t('routesView.form_subtype') }}</label>
              <select class="form-select" id="routeSubType" v-model="routeForm.sub_type">
                <option v-for="option in subTypeOptions" :key="option.value" :value="option.value">
                  {{ option.label }}
                </option>
              </select>
            </div>
            <div class="mb-3">
              <label for="routeDesc" class="form-label">{{ $t('routesView.form_desc') }}</label>
              <textarea class="form-control" id="routeDesc" rows="3" v-model="routeForm.description"></textarea>
            </div>
          </div>
          <div class="modal-footer">
            <button type="button" class="btn btn-secondary" @click="showSaveModal = false">{{ $t('routesView.form_cancel') }}</button>
            <button type="button" class="btn btn-primary" @click="saveRoute" :disabled="!routeForm.name || isSaving">
              <span v-if="isSaving" class="spinner-border spinner-border-sm me-2" role="status" aria-hidden="true"></span>
              {{ isEditMode ? t('routesView.form_submit_edit') : t('routesView.form_submit_create') }}
            </button>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { useI18n } from 'vue-i18n';
const { t, locale } = useI18n();
import { ref, onMounted, onUnmounted, computed, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import L from 'leaflet'
import 'leaflet/dist/leaflet.css'
import { routesService } from '@/services/routesService'
import { push } from 'notivue'


import iconRetinaUrl from 'leaflet/dist/images/marker-icon-2x.png'
import iconUrl from 'leaflet/dist/images/marker-icon.png'
import shadowUrl from 'leaflet/dist/images/marker-shadow.png'

delete L.Icon.Default.prototype._getIconUrl;
L.Icon.Default.mergeOptions({
  iconRetinaUrl,
  iconUrl,
  shadowUrl,
});

const router = useRouter()
const currentRoute = useRoute()


let map = null
let polyline = L.polyline([], { color: 'red', weight: 4 })
let markersLayer = L.layerGroup()

const OSRM_API = 'https://router.project-osrm.org/route/v1'

const waypoints = ref([])
const history = ref([])
const redoHistory = ref([])
const totalDistance = ref(0)
const allCoordinates = ref([])
const elevationGain = ref(0)
const elevationLoss = ref(0)

const autoRouting = ref(true)
const routingMode = ref('hybrid')
const showSaveModal = ref(false)
const isSaving = ref(false)
let elevationController = null
let elevationRequestToken = 0
let lastElevationKey = ''
let elevationDebounceTimer = null
let elevationCooldownUntil = 0
let lastElevationRateLimitNoticeAt = 0
const elevationCache = new Map()
const ELEVATION_DEBOUNCE_MS = 2500
const ELEVATION_COOLDOWN_MS = 20000
const SEARCH_SUGGESTIONS_LIMIT = 7
const SEARCH_DEBOUNCE_MS = 350
const INSERTION_DISTANCE_THRESHOLD_PX = 16
const ROUTE_SUB_TYPE_OPTIONS = {
  cycling: [
    { value: 'road', label: t('routesView.subtype_road_running') },
    { value: 'gravel', label: t('routesView.subtype_gravel') },
    { value: 'mountain_bike', label: t('routesView.subtype_mountain_bike') },
    { value: 'bikepacking', label: t('routesView.subtype_bikepacking') },
    { value: 'other', label: t('routesView.type_other') }
  ],
  running: [
    { value: 'road_running', label: t('routesView.subtype_road_running') },
    { value: 'trail_running', label: t('routesView.subtype_trail_running') },
    { value: 'interval', label: t('routesView.subtype_interval') },
    { value: 'long_run', label: t('routesView.subtype_long_run') },
    { value: 'other', label: t('routesView.type_other') }
  ],
  hiking: [
    { value: 'day_hike', label: t('routesView.subtype_day_hike') },
    { value: 'trekking', label: t('routesView.subtype_trekking') },
    { value: 'fast_hiking', label: t('routesView.subtype_fast_hiking') },
    { value: 'nordic_walking', label: t('routesView.subtype_nordic_walking') },
    { value: 'other', label: t('routesView.type_other') }
  ],
  other: [
    { value: 'other', label: t('routesView.type_other') }
  ]
}

const searchQuery = ref('')
const searchSuggestions = ref([])
const showSearchSuggestions = ref(false)
const isSearching = ref(false)
const isCalculating = ref(false)
let searchSuggestionsController = null
let searchSuggestionsDebounceTimer = null
let searchSuggestionHideTimer = null

const routeForm = ref({
  name: '',
  description: '',
  activity_type: 'cycling',
  sub_type: 'road'
})
const loadedRouteId = ref(null)

const isEditMode = computed(() => Boolean(currentRoute.params.id))
const pageTitle = computed(() => isEditMode.value ? t('routesView.title_edit') : t('routesView.title_create'))

const subTypeOptions = computed(() => {
  return ROUTE_SUB_TYPE_OPTIONS[routeForm.value.activity_type] || []
})


const startIcon = L.divIcon({
  className: 'custom-div-icon',
  html: `<div style="background-color: green; width: 20px; height: 20px; border-radius: 50%; border: 3px solid white; box-shadow: 0 0 5px rgba(0,0,0,0.5);"></div>`,
  iconSize: [20, 20],
  iconAnchor: [10, 10]
})

const defaultIcon = L.divIcon({
  className: 'custom-div-icon',
  html: `<div style="background-color: blue; width: 14px; height: 14px; border-radius: 50%; border: 2px solid white; box-shadow: 0 0 4px rgba(0,0,0,0.5);"></div>`,
  iconSize: [14, 14],
  iconAnchor: [7, 7]
})

const loopEndIcon = L.divIcon({
  className: 'custom-div-icon',
  html: `<div style="background-color: #dc3545; width: 16px; height: 16px; border-radius: 50%; border: 2px solid white; box-shadow: 0 0 4px rgba(0,0,0,0.5);"></div>`,
  iconSize: [16, 16],
  iconAnchor: [8, 8]
})

const canUndo = computed(() => waypoints.value.length > 0)
const canRedo = computed(() => redoHistory.value.length > 0)
const distanceLabel = computed(() => (totalDistance.value / 1000).toFixed(2))
const isLoopClosed = computed(() => {
  if (waypoints.value.length < 3) {
    return false
  }

  const first = waypoints.value[0]
  const last = waypoints.value[waypoints.value.length - 1]
  return first.lat === last.lat && first.lng === last.lng
})

const saveState = () => {
  history.value.push(JSON.parse(JSON.stringify(waypoints.value)))
  redoHistory.value = []
}

const invalidateRoutingSegments = () => {
  waypoints.value.forEach((wp) => {
    wp.segmentGeometry = null
    wp.segmentDistance = null
  })
}

const buildSearchSuggestion = (item) => {
  const address = item.address || {}
  const mainLabel = item.name || address.city || address.town || address.village || address.municipality || address.road || item.display_name?.split(',')?.[0] || t('routesView.search_result')
  const metaParts = [
    address.city || address.town || address.village || address.municipality,
    address.county || address.state_district || address.state,
    address.country,
    address.postcode
  ].filter(Boolean)

  return {
    id: item.place_id,
    label: mainLabel,
    meta: metaParts.join(' • '),
    lat: Number(item.lat),
    lon: Number(item.lon)
  }
}

const fetchSearchSuggestions = async (query) => {
  const trimmedQuery = query.trim()
  if (!trimmedQuery) {
    searchSuggestions.value = []
    showSearchSuggestions.value = false
    return []
  }

  if (searchSuggestionsController) {
    searchSuggestionsController.abort()
  }

  searchSuggestionsController = new AbortController()
  isSearching.value = true

  try {
    const params = new URLSearchParams({
      format: 'jsonv2',
      addressdetails: '1',
      limit: String(SEARCH_SUGGESTIONS_LIMIT),
      q: trimmedQuery,
      'accept-language': locale.value
    })
    const response = await fetch(
      `https://nominatim.openstreetmap.org/search?${params.toString()}`,
      { signal: searchSuggestionsController.signal }
    )

    if (!response.ok) {
      throw new Error(`Search request failed (${response.status})`)
    }

    const data = await response.json()
    const suggestions = Array.isArray(data) ? data.slice(0, SEARCH_SUGGESTIONS_LIMIT).map(buildSearchSuggestion) : []
    searchSuggestions.value = suggestions
    showSearchSuggestions.value = suggestions.length > 0
    return suggestions
  } catch (err) {
    if (err?.name !== 'AbortError') {
      console.error(err)
      searchSuggestions.value = []
      showSearchSuggestions.value = false
    }
    return []
  } finally {
    isSearching.value = false
  }
}

const handleSearchInput = () => {
  if (searchSuggestionHideTimer) {
    clearTimeout(searchSuggestionHideTimer)
  }

  if (searchSuggestionsDebounceTimer) {
    clearTimeout(searchSuggestionsDebounceTimer)
  }

  if (!searchQuery.value.trim()) {
    searchSuggestions.value = []
    showSearchSuggestions.value = false
    return
  }

  searchSuggestionsDebounceTimer = setTimeout(() => {
    fetchSearchSuggestions(searchQuery.value)
  }, SEARCH_DEBOUNCE_MS)
}

const handleSearchFocus = () => {
  if (searchSuggestions.value.length > 0) {
    showSearchSuggestions.value = true
  }
}

const scheduleHideSearchSuggestions = () => {
  if (searchSuggestionHideTimer) {
    clearTimeout(searchSuggestionHideTimer)
  }

  searchSuggestionHideTimer = setTimeout(() => {
    showSearchSuggestions.value = false
  }, 150)
}

const selectSearchSuggestion = (suggestion) => {
  searchQuery.value = suggestion.label
  showSearchSuggestions.value = false

  if (map) {
    map.setView([suggestion.lat, suggestion.lon], 13)
  }
}

const searchLocation = async () => {
  if (!searchQuery.value.trim()) return

  const suggestions = await fetchSearchSuggestions(searchQuery.value)
  if (suggestions.length > 0) {
    selectSearchSuggestion(suggestions[0])
    return
  }

  push.error(t('routesView.error_not_found'))
}

const loadRouteForEditing = async () => {
  if (!isEditMode.value) {
    return
  }

  try {
    const response = await routesService.getRoute(currentRoute.params.id)
    loadedRouteId.value = response.id
    routeForm.value = {
      name: response.name || '',
      description: response.description || '',
      activity_type: response.activity_type || 'cycling',
      sub_type: response.sub_type || 'other'
    }
    waypoints.value = JSON.parse(JSON.stringify(response.route_data?.waypoints || []))
    history.value = []
    redoHistory.value = []
    await updateMapVisuals()

    const coordinates = response.route_data?.coordinates || []
    if (map && coordinates.length > 1) {
      const latLngs = coordinates.map((coordinate) => [coordinate[1], coordinate[0]])
      map.fitBounds(latLngs, { padding: [30, 30] })
    }
  } catch (error) {
    console.error(error)
    push.error(t('routesView.error_load'))
    router.push({ name: 'routes-list' })
  }
}


const getRoutingBaseUrl = () => {
  const FOSSGIS = 'https://routing.openstreetmap.de'
  const OSRM    = 'https://router.project-osrm.org/route/v1'

  const isFoot =
    routeForm.value.activity_type === 'running' ||
    routeForm.value.activity_type === 'hiking' ||
    routeForm.value.activity_type === 'other'

  if (isFoot) {
    return routingMode.value === 'road'
      ? `${OSRM}/foot`
      : `${FOSSGIS}/routed-foot/route/v1/driving`
  }

  if (routingMode.value === 'road') return `${OSRM}/cycling`
  if (routingMode.value === 'path') return `${FOSSGIS}/routed-foot/route/v1/driving`
  return `${FOSSGIS}/routed-bike/route/v1/driving`
}

const setRoutingMode = (mode) => {
  if (routingMode.value === mode) return
  routingMode.value = mode
  invalidateRoutingSegments()
  updateMapVisuals()
}

const getWaypointSegmentLatLngs = (prevWaypoint, currentWaypoint) => {
  if (
    currentWaypoint.mode === 'auto' &&
    Array.isArray(currentWaypoint.segmentGeometry) &&
    currentWaypoint.segmentGeometry.length > 1
  ) {
    return currentWaypoint.segmentGeometry
      .map((coord) => {
        if (!Array.isArray(coord) || coord.length < 2) {
          return null
        }
        return L.latLng(Number(coord[1]), Number(coord[0]))
      })
      .filter((coord) => coord !== null)
  }

  return [
    L.latLng(prevWaypoint.lat, prevWaypoint.lng),
    L.latLng(currentWaypoint.lat, currentWaypoint.lng)
  ]
}

const getInsertionIndexFromClick = (clickLatLng) => {
  if (!map || waypoints.value.length < 2) {
    return -1
  }

  const clickPoint = map.latLngToContainerPoint(clickLatLng)
  let closestDistance = Number.POSITIVE_INFINITY
  let insertionIndex = -1

  for (let waypointIndex = 1; waypointIndex < waypoints.value.length; waypointIndex++) {
    const previousWaypoint = waypoints.value[waypointIndex - 1]
    const currentWaypoint = waypoints.value[waypointIndex]
    const segmentLatLngs = getWaypointSegmentLatLngs(previousWaypoint, currentWaypoint)

    for (let segmentIndex = 1; segmentIndex < segmentLatLngs.length; segmentIndex++) {
      const pointA = map.latLngToContainerPoint(segmentLatLngs[segmentIndex - 1])
      const pointB = map.latLngToContainerPoint(segmentLatLngs[segmentIndex])
      const distanceToSegment = L.LineUtil.pointToSegmentDistance(clickPoint, pointA, pointB)

      if (distanceToSegment < closestDistance) {
        closestDistance = distanceToSegment
        insertionIndex = waypointIndex
      }
    }
  }

  return closestDistance <= INSERTION_DISTANCE_THRESHOLD_PX ? insertionIndex : -1
}

const buildSampledCoordinates = (coordinates, maxPoints = 96) => {
  if (coordinates.length <= maxPoints) {
    return coordinates
  }

  const sampled = []
  const step = (coordinates.length - 1) / (maxPoints - 1)
  for (let i = 0; i < maxPoints; i++) {
    sampled.push(coordinates[Math.round(i * step)])
  }

  return sampled
}

const normalizeCoordinates = (coordinates) => {
  const normalized = []

  coordinates.forEach((coord) => {
    if (!Array.isArray(coord) || coord.length < 2) {
      return
    }

    const lon = Number(coord[0])
    const lat = Number(coord[1])
    if (!Number.isFinite(lon) || !Number.isFinite(lat)) {
      return
    }

    const previous = normalized[normalized.length - 1]
    if (previous && previous[0] === lon && previous[1] === lat) {
      return
    }

    normalized.push([lon, lat])
  })

  return normalized
}

const splitCoordinatesForElevation = (coordinates, chunkSize = 80) => {
  if (coordinates.length <= chunkSize) {
    return [coordinates]
  }

  const chunks = []
  const step = Math.max(2, chunkSize - 1)
  for (let start = 0; start < coordinates.length; start += step) {
    const end = Math.min(start + chunkSize, coordinates.length)
    chunks.push(coordinates.slice(start, end))

    if (end === coordinates.length) {
      break
    }
  }

  return chunks
}

const parseRetryAfterMs = (response) => {
  const retryAfterHeader = response.headers.get('Retry-After')
  const retryAfterSeconds = Number(retryAfterHeader)
  if (Number.isFinite(retryAfterSeconds) && retryAfterSeconds > 0) {
    return Math.round(retryAfterSeconds * 1000)
  }

  return ELEVATION_COOLDOWN_MS
}

const fetchElevationChunk = async (chunk, signal) => {
  const latitude = chunk.map((coord) => coord[1].toFixed(6)).join(',')
  const longitude = chunk.map((coord) => coord[0].toFixed(6)).join(',')
  const queryParams = new URLSearchParams({ latitude, longitude })

  const response = await fetch(
    `https://api.open-meteo.com/v1/elevation?${queryParams.toString()}`,
    { signal }
  )

  if (response.status === 429) {
    return {
      rateLimited: true,
      retryAfterMs: parseRetryAfterMs(response)
    }
  }

  if (!response.ok) {
    throw new Error(`Elevation request failed (${response.status})`)
  }

  const data = await response.json()
  const batchElevations = data?.elevation
  if (!Array.isArray(batchElevations) || batchElevations.length !== chunk.length) {
    throw new Error('Invalid elevation payload')
  }

  return {
    rateLimited: false,
    values: batchElevations
  }
}


const applyElevationsToAllCoordinates = (baseCoords, sampledCoords, elevations) => {
  if (!elevations || elevations.length !== sampledCoords.length) return baseCoords;
  let sIdx = 0;
  return baseCoords.map((coord) => {
    let bestDist = Infinity;
    let bestIdx = sIdx;
    for (let i = sIdx; i < sampledCoords.length; i++) {
       let dx = coord[0] - sampledCoords[i][0];
       let dy = coord[1] - sampledCoords[i][1];
       let dist = dx*dx + dy*dy;
       if (dist < bestDist) {
         bestDist = dist;
         bestIdx = i;
       }
       if (dist > bestDist + 0.0001) break;
    }
    sIdx = bestIdx;
    let ele = elevations[sIdx] || 0;
    return [coord[0], coord[1], ele];
  });
};

const updateElevation = async () => {


  if (elevationDebounceTimer) {
    clearTimeout(elevationDebounceTimer)
  }

  if (allCoordinates.value.length < 2) {
    elevationGain.value = 0
    elevationLoss.value = 0
    return
  }

  elevationDebounceTimer = setTimeout(async () => {
    if (Date.now() < elevationCooldownUntil) {
      return
    }

    if (allCoordinates.value.length < 2) {
      elevationGain.value = 0
      elevationLoss.value = 0
      return
    }

    const sampledCoordinates = normalizeCoordinates(buildSampledCoordinates(allCoordinates.value))
    if (sampledCoordinates.length < 2) {
      elevationGain.value = 0
      elevationLoss.value = 0
      return
    }

    const elevationKey = sampledCoordinates
      .map((coord) => `${coord[0].toFixed(5)}:${coord[1].toFixed(5)}`)
      .join('|')

    if (elevationKey === lastElevationKey) {
      return
    }

    const cachedElevation = elevationCache.get(elevationKey)
    if (cachedElevation) {
      elevationGain.value = cachedElevation.gain
      elevationLoss.value = cachedElevation.loss
      lastElevationKey = elevationKey
      return
    }

    lastElevationKey = elevationKey

    if (elevationController) {
      elevationController.abort()
    }

    elevationController = new AbortController()
    const currentToken = ++elevationRequestToken

    try {
      const chunks = splitCoordinatesForElevation(sampledCoordinates)
      const elevations = []

      for (let i = 0; i < chunks.length; i++) {
        const chunk = chunks[i]
        const result = await fetchElevationChunk(chunk, elevationController.signal)

        if (result.rateLimited) {
          elevationCooldownUntil = Date.now() + result.retryAfterMs
          const now = Date.now()
          if (now - lastElevationRateLimitNoticeAt > 15000) {
            push.error(t('routesView.error_elevation_429'))
            lastElevationRateLimitNoticeAt = now
          }

          lastElevationKey = ''
          return
        }


        if (i === 0) {
          elevations.push(...result.values)
        } else {
          elevations.push(...result.values.slice(1))
        }
      }

      if (currentToken !== elevationRequestToken) {
        return
      }

      if (!Array.isArray(elevations) || elevations.length < 2) {
        elevationGain.value = 0
        elevationLoss.value = 0
        return
      }

      let gain = 0
      let loss = 0

      for (let i = 1; i < elevations.length; i++) {
        const diff = elevations[i] - elevations[i - 1]
        if (diff > 0) {
          gain += diff
        } else {
          loss += Math.abs(diff)
        }
      }

      elevationGain.value = Math.round(gain)
      elevationLoss.value = Math.round(loss)
      allCoordinates.value = applyElevationsToAllCoordinates(allCoordinates.value, sampledCoordinates, elevations)
      elevationCache.set(elevationKey, {
        gain: elevationGain.value,
        loss: elevationLoss.value
      })
    } catch (error) {
      if (error?.name !== 'AbortError') {
        lastElevationKey = ''
        elevationGain.value = 0
        elevationLoss.value = 0
      }
    }
  }, ELEVATION_DEBOUNCE_MS)
}

const updateMapVisuals = async () => {
  isCalculating.value = true


  markersLayer.clearLayers()
  polyline.setLatLngs([])
  totalDistance.value = 0
  allCoordinates.value = []

  if (waypoints.value.length === 0) {
    lastElevationKey = ''
    elevationGain.value = 0
    elevationLoss.value = 0
    isCalculating.value = false
    return
  }


  waypoints.value.forEach((wp, index) => {
    const isStart = index === 0
    const isLoopEnd = isLoopClosed.value && index === waypoints.value.length - 1
    const marker = L.marker([wp.lat, wp.lng], {
        icon: isStart ? startIcon : (isLoopEnd ? loopEndIcon : defaultIcon),
        draggable: true
      })

      marker.on('contextmenu', () => {
        saveState()
        waypoints.value.splice(index, 1)
        if (index > 0 && waypoints.value[index - 1]) {
           waypoints.value[index - 1].segmentGeometry = null
        }
        updateMapVisuals()
      })

      marker.on('dragend', (e) => {
      saveState()
      const newPos = e.target.getLatLng()
      waypoints.value[index].lat = newPos.lat
      waypoints.value[index].lng = newPos.lng


        if (waypoints.value[index]) {
          waypoints.value[index].segmentGeometry = null
        }

        if (index + 1 < waypoints.value.length) {
          waypoints.value[index + 1].segmentGeometry = null
        }
        updateMapVisuals()
      })

      markersLayer.addLayer(marker)


      if(index === 0) {
        allCoordinates.value.push([wp.lng, wp.lat])
      }
    })


    let currentAccumulatedLatLngs = [L.latLng(waypoints.value[0].lat, waypoints.value[0].lng)]
    let tempDistance = 0;
    let tempCoordinates = waypoints.value.length > 0 ? [[waypoints.value[0].lng, waypoints.value[0].lat]] : [];

    const tempFallbackLine = (prev, curr, polylinePointsArray) => {
      const p1 = L.latLng(prev.lat, prev.lng)
      const p2 = L.latLng(curr.lat, curr.lng)
      tempDistance += p1.distanceTo(p2)
      tempCoordinates.push([curr.lng, curr.lat])
      polylinePointsArray.push(p2)
    }

    for (let i = 1; i < waypoints.value.length; i++) {
      const prev = waypoints.value[i-1]
      const curr = waypoints.value[i]

      if (curr.mode === 'auto') {
        if (!curr.segmentGeometry) {
          try {

            const baseUrl = getRoutingBaseUrl()
            const fetchUrl = `${baseUrl}/${prev.lng},${prev.lat};${curr.lng},${curr.lat}?overview=full&geometries=geojson`


            const controller = new AbortController()
            const timeoutId = setTimeout(() => controller.abort(), 3000)


            const response = await fetch(fetchUrl, {
              signal: controller.signal
            })
            clearTimeout(timeoutId)

            const data = await response.json()

            if (data.code === 'Ok') {
              const route = data.routes[0]
              curr.segmentDistance = route.distance
              curr.segmentGeometry = route.geometry.coordinates
            } else {
              curr.segmentGeometry = 'fallback'
            }
          } catch (err) {
            console.error('OSRM API Erreur', err)
             curr.segmentGeometry = 'fallback'
          }
        }

        if (curr.segmentGeometry && curr.segmentGeometry !== 'fallback') {
           tempDistance += curr.segmentDistance || 0
           const coords = curr.segmentGeometry

           for (let j = 1; j < coords.length; j++) {
             tempCoordinates.push([coords[j][0], coords[j][1]])
             currentAccumulatedLatLngs.push(L.latLng(coords[j][1], coords[j][0]))
           }
        } else {
            tempFallbackLine(prev, curr, currentAccumulatedLatLngs)
         }
      } else {
         tempFallbackLine(prev, curr, currentAccumulatedLatLngs)
      }
    }

    totalDistance.value = tempDistance;
    allCoordinates.value = tempCoordinates;
    polyline.setLatLngs(currentAccumulatedLatLngs);
    updateElevation()
    isCalculating.value = false;
  }

const closeLoop = () => {
  if (waypoints.value.length < 2 || isLoopClosed.value) {
    return
  }

  const startPoint = waypoints.value[0]
  saveState()
  waypoints.value.push({
    lat: startPoint.lat,
    lng: startPoint.lng,
    mode: autoRouting.value ? 'auto' : 'manual'
  })
  updateMapVisuals()
}
const undo = () => {
  if (!canUndo.value) return
  const current = JSON.parse(JSON.stringify(waypoints.value))
  redoHistory.value.push(current)

  if (history.value.length > 0) {
    waypoints.value = history.value.pop()
  } else {
    waypoints.value = []
  }
  updateMapVisuals()
}

const redo = () => {
  if (!canRedo.value) return
  history.value.push(JSON.parse(JSON.stringify(waypoints.value)))
  waypoints.value = redoHistory.value.pop()
  updateMapVisuals()
}

const onMapClick = (e) => {
  saveState()
  const insertionIndex = getInsertionIndexFromClick(e.latlng)
  const newWaypoint = {
    lat: e.latlng.lat,
    lng: e.latlng.lng,
    mode: waypoints.value.length === 0 ? 'start' : (autoRouting.value ? 'auto' : 'manual')
  }

  if (insertionIndex === -1) {
    waypoints.value.push(newWaypoint)
  } else {
    waypoints.value.splice(insertionIndex, 0, {
      ...newWaypoint,
      mode: autoRouting.value ? 'auto' : 'manual'
    })

    if (waypoints.value[insertionIndex]) {
      waypoints.value[insertionIndex].segmentGeometry = null
      waypoints.value[insertionIndex].segmentDistance = null
    }

    if (waypoints.value[insertionIndex + 1]) {
      waypoints.value[insertionIndex + 1].segmentGeometry = null
      waypoints.value[insertionIndex + 1].segmentDistance = null
    }
  }

  updateMapVisuals()
}

const saveRoute = async () => {
  if (waypoints.value.length < 2) return

  isSaving.value = true
  try {
    const payload = {
      name: routeForm.value.name,
      description: routeForm.value.description,
      activity_type: routeForm.value.activity_type,
      sub_type: routeForm.value.sub_type,
      distance: totalDistance.value,
      elevation_gain: elevationGain.value,
      route_data: {
        waypoints: waypoints.value,
        coordinates: allCoordinates.value,
        elevation_loss: elevationLoss.value
      }
    }

    const response = isEditMode.value
      ? await routesService.updateRoute(loadedRouteId.value, payload)
      : await routesService.createRoute(payload)
    push.success(isEditMode.value ? t('routesView.success_update') : t('routesView.success_create'))

    router.push({ name: 'route-detail', params: { id: response.id } })
  } catch (error) {
    console.error(error)
    push.error(isEditMode.value ? t('routesView.error_update') : t('routesView.error_save'))
  } finally {
    isSaving.value = false
    showSaveModal.value = false
  }
}

onMounted(() => {
  map = L.map('route-map').setView([48.8566, 2.3522], 13)
  setTimeout(() => { map.invalidateSize() }, 300)


  if (!isEditMode.value && "geolocation" in navigator) {
    navigator.geolocation.getCurrentPosition(position => {
      map.setView([position.coords.latitude, position.coords.longitude], 13)
    })
  }

  L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
    maxZoom: 19,
    attribution: '© OpenStreetMap contributors'
  }).addTo(map)

  polyline.addTo(map)
  markersLayer.addTo(map)

  map.on('click', onMapClick)

  loadRouteForEditing()
})

watch(
  () => routeForm.value.activity_type,
  () => {
    if (!subTypeOptions.value.some((option) => option.value === routeForm.value.sub_type)) {
      routeForm.value.sub_type = subTypeOptions.value[0]?.value || ''
    }

    if (waypoints.value.length > 1) {
      invalidateRoutingSegments()
      updateMapVisuals()
    }
  },
  { immediate: true }
)

onUnmounted(() => {
  if (searchSuggestionsDebounceTimer) {
    clearTimeout(searchSuggestionsDebounceTimer)
  }

  if (searchSuggestionHideTimer) {
    clearTimeout(searchSuggestionHideTimer)
  }

  if (searchSuggestionsController) {
    searchSuggestionsController.abort()
  }

  if (elevationDebounceTimer) {
    clearTimeout(elevationDebounceTimer)
  }

  if (elevationController) {
    elevationController.abort()
  }

  if (map) {
    map.remove()
  }
})
</script>

<style scoped>
.loading-bar {
  position: absolute;
  bottom: 0;
  left: 0;
  width: 100%;
  height: 5px;
  background: linear-gradient(90deg, transparent, #007bff, #00c6ff, transparent);
  background-size: 200% 100%;
  animation: loadingBg 1.5s infinite linear;
  z-index: 1000;
}
@keyframes loadingBg {
  0% { background-position: 100% 0; }
  100% { background-position: -100% 0; }
}
#route-map {
  cursor: crosshair;
  min-height: 600px;
}
.route-search-dropdown {
  position: absolute;
  top: calc(100% + 0.35rem);
  left: 0;
  right: 0;
  z-index: 1100;
  max-height: 22rem;
  overflow-y: auto;
  border-radius: 0.75rem;
}
</style>

