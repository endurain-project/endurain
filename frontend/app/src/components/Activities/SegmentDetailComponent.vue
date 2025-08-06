<template>
    <div v-if="isLoading">
        <LoadingComponent />
    </div>
    <div v-else>
    <!-- map zone -->
        <div class="mt-3 mb-3">
            <div ref="segmentMap" class="map rounded w-100" style="height: 500px;"></div>
        </div>
        <!-- Graph Zone -->
        <div class="mt-3 mb-3">
            <canvas ref="segmentTimeChart"></canvas>
        </div>
        <!-- Table Zone -->
        <div class="mt-3 mb-3">

        </div>
    </div>
</template>

<script setup>
import { ref, computed, onMounted, nextTick, watch, onUnmounted } from 'vue';
import { useI18n } from "vue-i18n";
import LoadingComponent from '@/components/GeneralComponents/LoadingComponent.vue';
import L from 'leaflet';
// Import Notivue push
import { push } from "notivue";
import { Chart, registerables } from 'chart.js';
Chart.register(...registerables);

const props = defineProps({
    activitySegments: {
        type: Object,
        required: true,
    },
    segment: {
        type: Object,
        required: true,
    }
});

const { t } = useI18n();
const isLoading = ref(true);
const segmentMap = ref(null);
const leafletMap = ref(null);
const segmentTimeChart = ref(null);

onMounted(async () => {
    try {
    } catch (error) {
        push.error(
            `${t("activityMapComponent.errorFetchingActivityStream")} - ${error}`,
        );
    } finally {
        isLoading.value = false;
        nextTick(() => {
            nextTick(() => {
                if (props.activitySegments) {
                    initMap();
                    initChart();
                }
            })
        })
    }
});

onUnmounted(() => {
    if (leafletMap.value) {
        leafletMap.value.remove();
        leafletMap.value = null;
    }
});

function formatDate(dateString) {
    const date = new Date(dateString);

    // Get the day, month (short), year (last two digits), hours, and minutes
    const day = date.getDate();
    const month = date.toLocaleDateString('default', { month: 'short' });
    const year = date.getFullYear().toString().slice(-2);
    const hours = date.getHours();
    const minutes = date.getMinutes().toString().padStart(2, '0');

    // Format the string
    return `${day} ${month} ${year} ${hours}:${minutes}`;
};

const initChart = () => {

    const labels = [];
    const segmentTimes = [];

    props.activitySegments.forEach(completion => {
        labels.push(formatDate(completion.start_time));
        segmentTimes.push(completion.segment_times[0]);
    });

    const datasets = [{
        label: t('segmentDetailComponent.timeInSeconds'),
        backgroundColor: 'transparent',
        borderColor: 'rgba(54, 162, 235, 0.8)',
        fill: true,
        fillColor: 'rgba(54, 162, 235, 0.2)',
        data: segmentTimes
    }];

    segmentTimeChart.value = new Chart(segmentTimeChart.value.getContext('2d'), {
        type: 'line',
        data: {
            labels: labels,
            datasets: datasets
        },
        options: {
            responsive: true,
            scales: {
                y: {
                    reverse: true,
                    beginAtZero: false,
                    position: 'left',
                    ticks: {
                        callback: function(value) {
                            const minutes = Math.floor(value / 60);
                            const seconds = value % 60;
                            return `${minutes}:${seconds < 10 ? '0' + seconds : seconds}`;
                        }
                    },
                    title: {
                        display: true,
                        text: t('segmentDetailComponent.timeInMinutes'),
                    }
                },
                x: {
                    autoSkip: true
                },
            }
        },
    });
};

const initMap = () => {
    if (!segmentMap.value) return;

    // Destroy previous map instance if exists
    if (leafletMap.value) {
        leafletMap.value.remove();
        leafletMap.value = null;
    }

    leafletMap.value = L.map(segmentMap.value, {
        dragging: false,
        touchZoom: false,
        scrollWheelZoom: false,
        zoomControl: false
    }).fitWorld();

    if (!leafletMap.value._completionPolylines) leafletMap.value._completionPolylines = [];

    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
        attribution: '© OpenStreetMap contributors'
    }).addTo(leafletMap.value);

    props.activitySegments.forEach(completion => {
        const waypoints = completion.stream_latlon;
        const validWaypoints = waypoints.filter(waypoint => waypoint.lat && waypoint.lon);

        const gpsPointIndexOrdered = completion.gps_point_index_ordered;
        const firstWaypointIndex = gpsPointIndexOrdered[0][1];
        const lastWaypointIndex = gpsPointIndexOrdered[gpsPointIndexOrdered.length - 1][0];

        const segmentWaypoints = validWaypoints.slice(firstWaypointIndex, lastWaypointIndex + 1);
        const latlngs = segmentWaypoints.map(waypoint => [waypoint.lat, waypoint.lon]);

        const completionPolyline = L.polyline(latlngs, { color: 'blue', weight: 1 }).addTo(leafletMap.value);

        leafletMap.value._completionPolylines.push(completionPolyline);
    });

    var gateLabel = 0;
    for (const gate of props.segment.gates) {
        // Ensure gate is an array with two points
        if (!Array.isArray(gate) || gate.length !== 2 || !Array.isArray(gate[0]) || !Array.isArray(gate[1]) || gate[0].length !== 2 || gate[1].length !== 2) {
            console.warn(`Invalid gate format for segment ${props.segment.id}:`, gate);
            continue;
        }

        const gateLatLngs = [
            [gate[0][0], gate[0][1]],
            [gate[1][0], gate[1][1]]
        ];

        // Create a label with the gate sequence number on the map
        if (gateLabel == 0) {
            const midGateLatLng = [
                (gateLatLngs[0][0] + gateLatLngs[1][0]) / 2,
                (gateLatLngs[0][1] + gateLatLngs[1][1]) / 2
            ];

            const label = L.marker(midGateLatLng, {
                icon: L.divIcon({ className: 'bg-success dot' })
            }).addTo(leafletMap.value);
            //leafletMap.value._gateLabels.push(label);

        }
        else if (gateLabel == props.segment.gates.length - 1) {
            const midGateLatLng = [
                (gateLatLngs[0][0] + gateLatLngs[1][0]) / 2,
                (gateLatLngs[0][1] + gateLatLngs[1][1]) / 2
            ];

            const label = L.marker(midGateLatLng, {
                icon: L.divIcon({ className: 'bg-danger dot' })
            }).addTo(leafletMap.value);
            //segmentIconMap._gateLabels.push(label);
        }
        else {
            // Create a polyline for the gate
            const polyline = L.polyline(gateLatLngs, {
                color: 'black',
                weight: 2,
                opacity: 1
            }).addTo(leafletMap.value);

            // Create markers for the start and end of the gate
            const label = L.marker(gateLatLngs[0]).addTo(leafletMap.value);
            label.setIcon(L.divIcon({
                className: 'leaflet-label',
                html: `<div style="background-color: white; border: 1px solid black; padding: 2px; border-radius: 5px; text-align: center;">
                        <span style="color: black; font-size: 12px;">${gateLabel}</span>
                    </div>`,
                iconSize: new L.Point(15, 15)
            }));
            //segmentIconMap._gateLabels.push(label);
        }

        gateLabel += 1;
    }

    if (leafletMap.value._completionPolylines.length > 0) {
        const latlngs = leafletMap.value._completionPolylines[0].getLatLngs();
        leafletMap.value.fitBounds(latlngs);
    }

};

</script>