<template>
    <div v-if="mapVisible==false">
        <div>
        Area for content if a Segment is active on the current map.<br>
        Hide this area if we're adding a new segment.
        </div>
        <div>
            <a class="w-100 btn btn-primary shadow-sm" role="button" @click="toggleSegmentAdd">
                {{ $t("activitySegmentsComponent.buttonAddSegment") }}
            </a>
        </div>
    </div>
    <div>
        <div style="cursor:crosshair" ref="mapContainer"></div>
        <br>
    </div>
    <div v-if="mapVisible">
        <div>
            <div class="card">
                <div class="card-body">
                    <div class="text-center">
                        {{ $t("activitySegmentsComponent.addSegmentDirections") }}
                    </div>
                    <div class="row row-gap-3">
                        <div class="col">
                            <form @submit.prevent="submitSegment">
                            <div class="row">&nbsp;</div>
                            <div class="row">
                                <div class="col">{{ $t("activitySegmentsComponent.inputSegmentName") }}</div>
                                <div class="col"><input class="form-control me-2" type="text" id="segmentName" v-model="segmentName"></div>
                            </div>
                            <div class="row">&nbsp;</div>
                            <div class="row">
                                <div class="col">
                                    <button type="submit" class="btn btn-primary" name="submitSegment">
                                        {{ $t("activitySegmentsComponent.buttonSubmitSegment") }}
                                    </button>
                                </div>
                                <div class="col">
                                    <a class="w-100 btn btn-primary shadow-sm" role="button" @click="toggleSegmentAdd">
                                        {{ $t("activitySegmentsComponent.buttonCancelSegment") }}
                                    </a>
                                </div>
                            </div>
                            </form>                    
                        </div>
                        <div class="col table-responsive d-none d-sm-block">
                            <div class="row">&nbsp;</div>
                            <div class="row">
                                <table class="table table-borderless table-hover table-sm rounded text-center" v-if="segmentPolylines.length > 0">
                                    <tbody>
                                        <tr v-for="(polyline, index) in segmentPolylines" :key="index">
                                            <td>Gate {{ index + 1 }}</td>
                                            <td>
                                                <a class="w-100 btn btn-primary shadow-sm" role="button" @click="deleteSegment(index)">
                                                    {{ $t("activitySegmentsComponent.buttonDeleteSegment") }}
                                                </a>
                                            </td>
                                        </tr>
                                    </tbody>
                                </table>
                            </div>
                        </div>
                    </div>
                </div>
            </div>
        </div>
    </div>
</template>

<script>
import { ref, toRef, onMounted, watchEffect, nextTick, vModelCheckbox } from 'vue';
import { activityStreams } from '@/services/activityStreams';
import LoadingComponent from '@/components/GeneralComponents/LoadingComponent.vue';
import { segments } from '@/services/activitySegmentsService';
// Importing the stores
import { useAuthStore } from "@/stores/authStore";
import { push } from "notivue";
import { useI18n } from "vue-i18n";
import L from 'leaflet';
import { polyline } from 'leaflet';
//const { t } = useI18n();

export default {
    data() {
        return {
            map: null,
            mapVisible: false,
            activityStreamLatLng: null,
            segmentPolylines: [],
            segmentPolylinePoints: [],
            markers: {},
            segmentName: '',
        }
    },
    props: {
        activity: {
            type: Object,
            required: true,
        }
    },
    methods: {
        async submitSegment(){
            try {
                const gates = [];
                this.segmentPolylines.forEach(polyline => {
                    const latlngs = polyline.getLatLngs();
                    gates.push([[latlngs[0].lat, latlngs[0].lng],[latlngs[1].lat, latlngs[1].lng]]);
                });

                const data = {
                    name: this.segmentName,
                    activity_type: this.activity.activity_type,
                    gates: gates,
                };
                const submittedSegment = await segments.createSegment(data);
            } catch (error){
                //push.error(`${t("activitySegmentsComponent.errorSubmitSegment")} - ${error}`);
                console.error(error);
            } finally {
            }
        },
        deleteSegment(index){
            const polyline = this.segmentPolylines[index];
            this.map.removeLayer(polyline);
            this.segmentPolylines.splice(index,1);

            this.map.removeLayer(this.markers[polyline._leaflet_id][0]);
            this.map.removeLayer(this.markers[polyline._leaflet_id][1]);
            delete this.markers[polyline._leaflet_id];

        },
        async createMap(activity) {
    		const authStore = useAuthStore();
            const activityStreamLatLng = ref(null);

            if (authStore.isAuthenticated) {
                activityStreamLatLng.value = await activityStreams.getActivitySteamByStreamTypeByActivityId(activity.id, 7);
            } else {
                activityStreamLatLng.value = await activityStreams.getPublicActivitySteamByStreamTypeByActivityId(activity.id, 7);
            }

            const waypoints = activityStreamLatLng.value.stream_waypoints;
            const validWaypoints = waypoints.filter(waypoint => waypoint.lat && waypoint.lon);
            const latlngs = validWaypoints.map(waypoint => [waypoint.lat, waypoint.lon]);
            
            this.map = L.map(this.$refs.mapContainer,
            {
                dragging: true,
                touchZoom: true,
                scrollWheelZoom: true,
                zoomControl: true,
            }).fitWorld();

            L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
                attribution: 'Map data &copy; <a href="https://www.openstreetmap.org/">OpenStreetMap</a>',
                subdomains: ['a', 'b', 'c']
            }).addTo(this.map);

            L.polyline(latlngs, { color: 'blue' }).addTo(this.map);

            // Fit map to polyline bounds
            if (latlngs.length > 0) {
                this.map.fitBounds(latlngs);

                // Add start and end markers
                L.marker(latlngs[0], {
                    icon: L.divIcon({ className: 'bg-success dot' })
                }).addTo(this.map);

                L.marker(latlngs[latlngs.length - 1], {
                    icon: L.divIcon({ className: 'bg-danger dot' })
                }).addTo(this.map);
            }

            this.map.on('click', (e) => {

                const latlng = e.latlng;

                if (this.point1 == null){
                    this.point1 = latlng;
                } else
                {
                    let vertexMarkers = [];
                    const polylinePoints = [this.point1, latlng];

                    function updatePolylineOnMarkerDrag() {
                        const newPoints = [];
                        vertexMarkers.forEach(marker=> {
                            newPoints.push(marker.getLatLng());
                        });
                        line.setLatLngs(newPoints);
                        this.semgentPolylinePoints = polylinePoints;
                    }

                    const line = L.polyline(polylinePoints, {
                        color: 'red'
                    }).addTo(this.map);
                    this.segmentPolylinePoints = polylinePoints;
                    line.options.id = this.segmentPolylines.length;

                    const marker1 = L.marker(polylinePoints[0]).addTo(this.map);
                    const marker2 = L.marker(polylinePoints[1]).addTo(this.map);

                    this.markers[line._leaflet_id] = [marker1, marker2];

                    marker1.dragging.enable();
                    marker2.dragging.enable();
                    vertexMarkers.push(marker1);
                    vertexMarkers.push(marker2);
                    marker1.on('drag', updatePolylineOnMarkerDrag);
                    marker2.on('drag', updatePolylineOnMarkerDrag);

                    this.segmentPolylines.push(line);
                    this.point1 = null;
                }
            });
        },
        async toggleSegmentAdd() {
            this.mapVisible = !this.mapVisible;
            if (this.mapVisible) {
                this.$refs.mapContainer.style.height = '600px';
                this.$refs.mapContainer.style.width = '100%';
                await this.createMap(this.activity);
                this.map.invalidateSize();
            } else {
                this.map.remove();
                this.map = null;
                this.$refs.mapContainer.style.height = '0px';
                this.segmentPolylines = [];
                this.markers = {};
            }
        }
    }
}
</script>