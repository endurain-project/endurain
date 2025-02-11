<template>
    <!-- map zone -->
    <div v-if="isLoading">
        <LoadingComponent />
    </div>
    <div v-else-if="activityStreamLatLng">
        <div ref="activityMap" class="map" style="height: 300px;" v-if="source === 'home'"></div>
        <div ref="activityMap" class="map" style="height: 500px;" v-if="source === 'activity'"></div>
    </div>
</template>

<script>
import { ref, onMounted, watchEffect, nextTick } from 'vue';
import { activityStreams } from '@/services/activityStreams';
import LoadingComponent from '@/components/GeneralComponents/LoadingComponent.vue';
import L from 'leaflet';
// Importing the stores
import { useAuthStore } from "@/stores/authStore";

export default {
    components: {
        LoadingComponent,
    },
    props: {
        activity: {
            type: Object,
            required: true,
        },
        source:{
            type: String,
            required: true,
        }
    },
    setup(props) {
		const authStore = useAuthStore();
        const isLoading = ref(true);
        const activityStreamLatLng = ref(null);
        const activityMap = ref(null);

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

        return {
            isLoading,
            activityStreamLatLng,
            activityMap,
        };
    },
};
</script>