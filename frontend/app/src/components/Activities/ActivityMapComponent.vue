<template>
    <!-- map zone -->
    <div v-if="isLoading">
        <LoadingComponent />
    </div>
    <div v-else-if="activityStreamLatLng">
        <div ref="activityMap" class="map rounded" style="height: 300px;" v-if="source === 'home'"></div>
        <div ref="activityMap" class="map rounded" style="height: 500px;" v-if="source === 'activity'"></div>
    </div>
</template>

<script>
import { ref, onMounted, watchEffect, nextTick } from 'vue';
import { activityStreams } from '@/services/activityStreams';
import { segments } from '@/services/activitySegmentsService';
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
        const activitySegments = [ref(null)];
        const activityMap = ref(null);

        onMounted(async () => {
            try {
                if (authStore.isAuthenticated) {
                    activityStreamLatLng.value = await activityStreams.getActivitySteamByStreamTypeByActivityId(props.activity.id, 7);
                    if (props.source == 'activity') {
                        activitySegments.values = await segments.getActivitySegments (props.activity.id);
                    }
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

            const boundpoints = [];
            // Sequence of colors to differentiate between 
            const segmentColors = ['teal', 'orange', 'pink', 'red', 'purple'];
            var segmentColorIdx = 0;

            if (props.source == 'activity')
            {
                const segmentArr = activitySegments.values
                // Iterate through segments that have been returned for this gps trace
                for (const segment in segmentArr) {
                    // Set the color of the map annotations
                    if (segment == 0) {
                        segmentColorIdx = 0;
                    } else {
                        segmentColorIdx += 1;
                        if (segmentColorIdx > segmentColors.length - 1) {
                            segmentColorIdx = 0;
                        }
                    }
                    // Iterate through the gates that have been defined for the segments
                    for (const gate in segmentArr[segment]['gates']) {
                        // Increment the gate number as it's label. First gate is labelled as 1, second is 2 etc...
                        var gateLabel = Number(gate) + 1;
                        // Draw the gate on the map
                        var gateLine = L.polyline(segmentArr[segment]['gates'][gate], { color: segmentColors[segmentColorIdx]}).addTo(map);
                        // Create a marker with the gate sequence number on the map
                        var label = L.marker(gateLine.getLatLngs()[0]).addTo(map);
                        label.setIcon(L.divIcon({
                            className: 'leaflet-label',
                            html: '<div style="background-color: white; border: 1px solid black; padding: 2px; border-radius: 5px; text-align: center;"><span style="color: black; font-size: 12px; font-weight: bold;">'+gateLabel+'</span></div>',
                            iconSize: new L.Point(15, 15)
                        }));
                        // Add segment to a boundpoints array, in case we want to fit the map to the segment
                        // This is a helper for use in other areas. TODO: Remove from this area.
                        boundpoints.push(segmentArr[segment]['gates'][gate][0]);
                        boundpoints.push(segmentArr[segment]['gates'][gate][1]);
                    }
                }
            }

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