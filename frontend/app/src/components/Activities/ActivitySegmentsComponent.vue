<template>
    <div v-if="mapVisible==false">
        <div>
            <div class="card">
                <div class="card-body">
                    <div class="text-center" v-if="segmentsFollowed.length == 0">
                        {{ $t("activitySegmentsComponent.activityNotFollowingDefinedSegments") }}
                    </div>
                    <div class="table-responsive d-none d-sm-block" ref="activitySegments" id="activitySegments" v-else>
                        <table class="table table-borderless table-hover table-sm rounded text-center" v-if="segmentsFollowed.length > 0">
                            <thead>
                                <tr>
                                    <th>{{ $t("activitySegmentsComponent.labelSegmentName") }}</th>
                                    <th></th>
                                </tr>
                            </thead>
                            <tbody>
                                <tr v-for="segment in segmentsFollowed" :key="segment.id">
                                    <td align="center">
                                        {{ segment.name }}
                                        <div :ref="`segmentMapIcon-${segment.id}`" :id="`segmentMapIcon-${segment.id}`"></div>
                                    </td>
                                    <td></td>
                                </tr>
                            </tbody>
                        </table>
                    </div>
                </div>
            </div>
        </div>
        <div>
            <br>
            <a class="w-100 btn btn-primary shadow-sm" role="button" @click="toggleSegmentAdd">
                {{ $t("activitySegmentsComponent.buttonAddSegment") }}
            </a>
        </div>
    </div>
    <div>
        <div>
            <div style="cursor:crosshair" ref="mapContainer"></div>
            <br>
        </div>
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
import { segments } from '@/services/activitySegmentsService';
// Importing the stores
import { useAuthStore } from "@/stores/authStore";
import { push } from "notivue";
import { useI18n } from "vue-i18n";
import L from 'leaflet';
//const { t } = useI18n();

export default {
    mounted() {
        this.$nextTick(() => {
                const observer = new ResizeObserver((entries, observer) => {
                    for (let entry of entries) {
                        if (entry.target === this.$refs.activitySegments) {
                            // Check if the height of the div has changed
                            this.onActivitySegmentsVisibleChange();
                        }
                    }
                    // Call checkheight to ensure the height is checked after resize
                    this.onActivitySegmentsVisibleChange();
                });
            setTimeout(() => {
                observer.observe(this.$refs.activitySegments);
            }, 1000);
        });

        // Fetch activity segments when the component is mounted
        this.fetchActivitySegments();

        // Watch for changes in segmentsFollowed and create segment icon maps
        this.$watch('segmentsFollowed', (newValue, oldValue) => {
            // Ensure the map is created after segmentsFollowed is populated
            if (newValue.length > 0) {
                this.updateSegmentIconMaps(this.segmentsFollowed);
            }
        });
    },
    data() {
        return {
            map: null,
            mapVisible: false,
            activityStreamLatLng: null,
            segmentsFollowed: [],
            segmentsMaps: [],
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
        updateSegmentIconMaps(segments) {
            var segmentNumber = 0;
            
            segments.forEach(segment => {
                setTimeout(() => {
                    // Ensure the map is rendered after the DOM is updated
                    this.createSegmentIconMap(segment, segmentNumber);
                    segmentNumber++;
                }, 200);
            });
        },
        onActivitySegmentsVisibleChange() {

            for (let i = 0; i < this.segmentsMaps.length; i++) {
                const segmentMap = this.segmentsMaps[i];
                if (segmentMap) {
                    segmentMap.invalidateSize();
                }
            }
        },
        async fetchActivitySegments() {
            const authStore = useAuthStore();
            try {
                if (authStore.isAuthenticated) {
                    this.segmentsFollowed = await segments.getActivitySegments(this.activity.id);
                }
            } catch (error) {
                console.error("Failed to fetch activity segments:", error);
            }
        },
        async createSegmentIconMap(segment, segmentNumber) {
            // Check if the ref for the segment map icon exists
            if (!this.$refs[`segmentMapIcon-${segment.id}`]) {
                console.warn(`No ref found for segmentMapIcon-${segment.id}`);
                return;
            }

            // Ensure the map container is ready
            await this.$nextTick();

            // Fetch activity stream data

    		const authStore = useAuthStore();
            const activityStreamLatLng = ref(null);

            if (authStore.isAuthenticated) {
                activityStreamLatLng.value = await activityStreams.getActivitySteamByStreamTypeByActivityId(this.activity.id, 7);
            } else {
                activityStreamLatLng.value = await activityStreams.getPublicActivitySteamByStreamTypeByActivityId(this.activity.id, 7);
            }

            const waypoints = activityStreamLatLng.value.stream_waypoints;
            const validWaypoints = waypoints.filter(waypoint => waypoint.lat && waypoint.lon);
            const latlngs = validWaypoints.map(waypoint => [waypoint.lat, waypoint.lon]);

            const mapCont = this.$refs[`segmentMapIcon-${segment.id}`][0];

            mapCont.style.height = '200px';
            mapCont.style.width = '200px';

            const segmentIconMap = L.map(mapCont,
            {
                dragging: false,
                boxZoom: false,
                touchZoom: false,
                doubleClickZoom: false,
                scrollWheelZoom: false,
                zoomControl: false,
            }).fitWorld();

            L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
                attribution: '© OpenStreetMap'
            }).addTo(segmentIconMap);

            L.polyline(latlngs, { 
                color: 'blue',
                weight: 2,
                opacity: 0.2
            }).addTo(segmentIconMap);

            const boundpoints = [];
            // Sequence of colors to differentiate between
            // TODO: Centralize this array to a common place
            const segmentColors = ['orange', 'purple', 'pink', 'red'];
            const segmentColorIdx = segmentNumber % segmentColors.length;

            var gateLabel = 1;
            for (const gate of segment.gates) {
                // Ensure gate is an array with two points
                if (!Array.isArray(gate) || gate.length !== 2 || !Array.isArray(gate[0]) || !Array.isArray(gate[1]) || gate[0].length !== 2 || gate[1].length !== 2) {
                    console.warn(`Invalid gate format for segment ${segment.id}:`, gate);
                    continue;
                }                
                const gateLatLngs = [
                    [gate[0][0], gate[0][1]],
                    [gate[1][0], gate[1][1]]
                ];
                // Create a polyline for the gate
                const polyline = L.polyline(gateLatLngs, {
                    color: segmentColors[segmentColorIdx],
                    weight: 4,
                    opacity: 1
                }).addTo(segmentIconMap);

                // Create markers for the start and end of the gate
                var label = L.marker(gateLatLngs[0]).addTo(segmentIconMap);
                // Create a label with the gate sequence number on the map
                label.setIcon(L.divIcon({
                    className: 'leaflet-label',
                    html: '<div style="background-color: white; border: 1px solid black; padding: 2px; border-radius: 5px; text-align: center;"><span style="color: black; font-size: 12px; font-weight: bold;">'+gateLabel+'</span></div>',
                    iconSize: new L.Point(15, 15)
                }));

                boundpoints.push(gateLatLngs[0]);
                boundpoints.push(gateLatLngs[1]);

                gateLabel += 1;
            }

            // Add the segment polyline to the map
            segmentIconMap.fitBounds(boundpoints);

            segmentIconMap.on('resize', () => {
                // Ensure the map is properly sized after rendering
                segmentIconMap.fitBounds(boundpoints);
            });

            this.segmentsMaps.push(segmentIconMap);
        },
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
        async createAddSegmentMap(activity) {

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
                attribution: '© OpenStreetMap contributors'
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
                await this.createAddSegmentMap(this.activity);
                this.map.invalidateSize();
            } else {
                this.map.remove();
                this.map = null;
                this.$refs.mapContainer.style.height = '0px';
                this.segmentPolylines = [];
                this.markers = {};
                this.segmentsFollowed = [];
                this.fetchActivitySegments();
            }
        }
    }
}
</script>