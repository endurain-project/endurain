<template>
    <!-- map zone -->
    <div v-if="isLoading">
        <LoadingComponent />
    </div>
    <div v-else-if="activityStreamLatLng">
        <div ref="activityMap" class="map" style="height: 300px;" v-if="sourceProp === 'home'"></div>
        <div ref="activityMap" class="map" style="height: 500px;" v-if="sourceProp === 'activity'"></div>
    </div>
</template>

<script>
import { ref, onMounted, watchEffect, nextTick } from 'vue';
import { activityStreams } from '@/services/activityStreams';
import LoadingComponent from '@/components/GeneralComponents/LoadingComponent.vue';
import L from 'leaflet';

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
        const isLoading = ref(true);
        const activityStreamLatLng = ref(null);
        const activityMap = ref(null);
        const sourceProp = ref(props.source);

        onMounted(async () => {
            try {
                activityStreamLatLng.value = await activityStreams.getActivitySteamByStreamTypeByActivityId(props.activity.id, 7);
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
                dragging: false, // Disable panning
                touchZoom: false, // Disable touch zoom
                scrollWheelZoom: false, // Disable scroll wheel zoom
                zoomControl: false // Remove zoom control buttons
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
            sourceProp,
        };
    },
};
</script>