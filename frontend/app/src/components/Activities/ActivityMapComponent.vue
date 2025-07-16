<template>
    <!-- map zone -->
    <div v-if="isLoading">
        <LoadingComponent />
    </div>
    <div v-else>
        <div v-if="hasGalleryItems">
            <div id="activityGallery" class="carousel slide" data-bs-ride="carousel">
                <div class="carousel-inner">
                    <!-- Map as first item -->
                    <div v-if="activityStreamLatLng" class="carousel-item active">
                        <div ref="activityMap" class="map rounded w-100" style="height: 300px;"
                            v-if="source === 'home'"></div>
                        <div ref="activityMap" class="map rounded w-100" style="height: 500px;"
                            v-if="source === 'activity'"></div>
                    </div>
                    <!-- Media items -->
                    <div v-for="(mediaItem, idx) in activityActivityMedia" :key="mediaItem.id || idx"
                        class="carousel-item" :class="{ active: !activityStreamLatLng && idx === 0 }"
                        :style="{ height: source === 'home' ? '300px' : '500px' }">
                        <img :src="`${endurainHost}${mediaItem.media_path.split('/').slice(1).join('/')}`"
                            class="d-block w-100 rounded" alt="Activity media"
                            :style="{ height: source === 'home' ? '300px' : '500px', objectFit: 'contain' }" />
                    </div>
                </div>
                <button class="carousel-control-prev" type="button" data-bs-target="#activityGallery"
                    data-bs-slide="prev">
                    <span class="carousel-control-prev-icon" aria-hidden="true"></span>
                    <span class="visually-hidden">Previous</span>
                </button>
                <button class="carousel-control-next" type="button" data-bs-target="#activityGallery"
                    data-bs-slide="next">
                    <span class="carousel-control-next-icon" aria-hidden="true"></span>
                    <span class="visually-hidden">Next</span>
                </button>
            </div>
        </div>
        <div v-else-if="activityStreamLatLng">
            <div ref="activityMap" class="map rounded w-100" style="height: 300px;" v-if="source === 'home'"></div>
            <div ref="activityMap" class="map rounded w-100" style="height: 500px;" v-if="source === 'activity'"></div>
        </div>
    </div>
    <!--<div v-else-if="activityStreamLatLng">
        <div ref="activityMap" class="map rounded" style="height: 300px;" v-if="source === 'home'"></div>
        <div ref="activityMap" class="map rounded" style="height: 500px;" v-if="source === 'activity'"></div>
    </div>-->
</template>

<script setup>
import { ref, computed, onMounted, watchEffect, nextTick } from 'vue';
import { activityStreams } from '@/services/activityStreams';
import LoadingComponent from '@/components/GeneralComponents/LoadingComponent.vue';
import L from 'leaflet';
import { useAuthStore } from "@/stores/authStore";

// Props declaration
const props = defineProps({
    activity: {
        type: Object,
        required: true,
    },
    activityActivityMedia: {
        type: Array,
        default: () => [],
    },
    source: {
        type: String,
        required: true,
    }
});

const authStore = useAuthStore();
const isLoading = ref(true);
const activityStreamLatLng = ref(null);
const activityMap = ref(null);
const hasGalleryItems = computed(() => {
    if (!props.activityActivityMedia || !Array.isArray(props.activityActivityMedia) || props.activityActivityMedia.length === 0) {
        return false;
    }
    return !!activityStreamLatLng.value || (Array.isArray(props.activityActivityMedia) && props.activityActivityMedia.length > 0);
});
console.log(hasGalleryItems.value)
const endurainHost = `${window.env.ENDURAIN_HOST}/`;

onMounted(async () => {
    try {
        if (authStore.isAuthenticated) {
            activityStreamLatLng.value = await activityStreams.getActivitySteamByStreamTypeByActivityId(props.activity.id, 7);
        } else {
            activityStreamLatLng.value = await activityStreams.getPublicActivitySteamByStreamTypeByActivityId(props.activity.id, 7);
        }
    } catch (error) {
        console.error("Failed to fetch activity details:", error);
    } finally {
        isLoading.value = false;
        nextTick(() => {
            nextTick(() => {
                if (activityStreamLatLng.value) {
                    initMap();
                }
            });
        });
    }
});

watchEffect(() => {
    // Empty watchEffect, kept for potential future use
});

const initMap = () => {
    if (!activityMap.value) return;

    const waypoints = activityStreamLatLng.value.stream_waypoints;

    const validWaypoints = waypoints.filter(waypoint => waypoint.lat && waypoint.lon);

    const latlngs = validWaypoints.map(waypoint => [waypoint.lat, waypoint.lon]);

    const map = L.map(activityMap.value, {
        dragging: props.source === 'activity', // Enable if 'activity', disable if 'home'
        touchZoom: props.source === 'activity', // Enable if 'activity', disable if 'home'
        scrollWheelZoom: props.source === 'activity', // Enable if 'activity', disable if 'home'
        zoomControl: props.source === 'activity' // Enable if 'activity', disable if 'home'
    }).fitWorld();

    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
        attribution: '© OpenStreetMap contributors'
    }).addTo(map);

    L.polyline(latlngs, { color: 'blue' }).addTo(map);

    // Fit map to polyline bounds
    if (latlngs.length > 0) {
        map.fitBounds(latlngs);

        // Add start and end markers
        L.marker(latlngs[0], {
            icon: L.divIcon({ className: 'bg-success dot' })
        }).addTo(map);

        L.marker(latlngs[latlngs.length - 1], {
            icon: L.divIcon({ className: 'bg-danger dot' })
        }).addTo(map);
    }
};
</script>