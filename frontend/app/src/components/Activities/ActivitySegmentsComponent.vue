<template>
    <div v-if="isLoading">
        <LoadingComponent />
    </div>
    <div v-else>
        <div v-if="mapVisible==false">
            <div v-if="intersections">
                <div class="text-center" v-if="intersections.length == 0">
                    <NoItemsFoundComponents v-if="intersections.length == 0"/>
                </div>
                <div class="container-fluid d-flex justify-content-center align-items-stretch" ref="activitySegments" id="activitySegments" v-else>
                    <table v-if="intersections.length > 0">
                        <tbody>
                            <tr v-for="(intersection, idx) in intersections" :key="intersection.id">
                                <td>
                                    <table>
                                        <thead>
                                            <tr>
                                                <th class="text-center m-10" colspan="3">
                                                    <router-link :to="{name: 'segment', params: {id: intersection.segment_id } }" class="link-body-emphasis link-underline-opacity-0 link-underline-opacity-100-hover">{{ intersection.segment_name }}</router-link>
                                                </th>
                                            </tr>
                                        </thead>
                                        <tbody>
                                            <tr>
                                                <td class="text-center m-10" colspan="3">
                                                    {{ $t("activitySegmentsComponent.labelStartTime") }}: {{ formatDateTime(intersection.start_time) }}
                                                </td>
                                            </tr>
                                            <tr>
                                                <td class="m-10">
                                                    <div :ref="`segmentMapIcon-${intersection.segment_id}-${intersection.lap_number}`" :id="`segmentMapIcon-${intersection.segment_id}-${intersection.lap_number}`"></div>
                                                </td>
                                                <td>&nbsp;</td>
                                                <td class="m-10">
                                                    <table class="table w-100 table-borderless table-hover table-sm rounded text-center" :class="{ 'table-striped': activity.activity_type !==8 }" style="--bs-table-bg: var(--bs-gray-850);" v-if="intersection && intersection.sub_segment_times">
                                                        <thead>
                                                            <tr>
                                                                <th>{{ $t("activitySegmentsComponent.labelInterval") }}</th>
                                                                <th>{{ $t("activitySegmentsComponent.labelTimeElapsed") }}</th>
                                                                <th>{{ $t("activitySegmentsComponent.labelTimeInterval") }}</th>
                                                                <th>{{ $t("activitySegmentsComponent.labelSpeedPace") }}</th>
                                                            </tr>
                                                        </thead>
                                                        <tbody class="table-group-divider">
                                                            <tr v-for="subSegmentIdx in intersection.sub_segment_times.length" @mouseover="highlightGate(idx, subSegmentIdx, intersection.gate_ordered[subSegmentIdx])" @mouseout="unhighlightGate(idx, subSegmentIdx, intersection.gate_ordered[subSegmentIdx])">
                                                                <td>
                                                                    {{ (subSegmentIdx === intersection.sub_segment_times.length)? $t("activitySegmentsComponent.labelFinish") : intersection.gate_ordered[subSegmentIdx] }}
                                                                </td>
                                                                <td>
                                                                    {{ formatSecondsToTime(intersection.sub_segment_times[subSegmentIdx-1]) }}
                                                                </td>
                                                                <td>
                                                                    {{ (subSegmentIdx === 1)? formatSecondsToTime(intersection.sub_segment_times[subSegmentIdx-1]) : formatSecondsToTime(intersection.sub_segment_times[subSegmentIdx-1] - intersection.sub_segment_times[subSegmentIdx-2])
                                                                        }}
                                                                </td>
                                                                <td>
                                                                    {{ formatSpeed(intersection.sub_segment_paces[subSegmentIdx-1], activity.activity_type, authStore.user.units) }}
                                                                </td>
                                                            </tr>
                                                        </tbody>
                                                    </table>
                                                </td>
                                            </tr>
                                        </tbody>
                                    </table>
                                </td>
                            </tr>
                        </tbody>
                    </table>
                </div>
            </div>
            <div>
                <br>
                <a class="w-100 btn btn-primary shadow-sm" role="button" @click="toggleSegmentAdd">
                    {{ $t("activitySegmentsComponent.buttonAddSegment") }}
                </a>
            </div>
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
            <div class="text-center">
                {{ $t("activitySegmentsComponent.addSegmentDirections") }}
            </div>
            <div class="row row-gap-3">
                <div class="col">
                    <form @submit.prevent="submitSegment">
                    <div class="row my-3">
                        <div class="col">{{ $t("activitySegmentsComponent.inputSegmentName") }}</div>
                        <div class="col"><input class="form-control me-2" type="text" id="segmentName" v-model="segmentName"></div>
                    </div>
                    <div class="row my-2">
                        <div class="col">{{ $t("activitySegmentsComponent.inputSegmentTown") }}</div>
                        <div class="col"><input class="form-control me-2" type="text" id="segmentTown" v-model="segmentTown"></div>
                    </div>
                    <div class="row my-2">
                        <div class="col">{{ $t("activitySegmentsComponent.inputSegmentCity") }}</div>
                        <div class="col"><input class="form-control me-2" type="text" id="segmentCity" v-model="segmentCity"></div>
                    </div>
                    <div class="row my-2">
                        <div class="col">{{ $t("activitySegmentsComponent.inputSegmentCountry") }}</div>
                        <div class="col"><input class="form-control me-2" type="text" id="segmentCountry" v-model="segmentCountry"></div>
                    </div>
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
</template>

<script>
import { ref } from 'vue';
import { activityStreams } from '@/services/activityStreams';
import { activitySegments } from '@/services/activitySegmentsService';
// Importing the stores
import { useAuthStore } from "@/stores/authStore";
import LoadingComponent from "@/components/GeneralComponents/LoadingComponent.vue";
import NoItemsFoundComponents from "@/components/GeneralComponents/NoItemsFoundComponents.vue";
import L from 'leaflet';
//const { t } = useI18n();
import {
	formatDateTime,
} from "@/utils/activityUtils";
import { 
    formatSecondsToTime,
    formatSpeed,
 } from "@/utils/segmentUtils";
import { faL } from '@fortawesome/free-solid-svg-icons';

export default {
    components: {
        NoItemsFoundComponents,
        LoadingComponent,
    },
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
                const el = this.$refs.activitySegments;
                if (el && el instanceof Element) {
                    observer.observe(el);
                } else {
                    //console.warn("activitySegments ref is not a valid Element");
                }
            }, 2000);
        });

        // Fetch activity segments when the component is mounted
        this.fetchActivitySegments();
        this.isLoading = false;
    },
    data() {
        return {
            authStore: useAuthStore(),
            isLoading: true,
            map: null,
            mapVisible: false,
            activityStreamLatLng: null,
            segmentsFollowed: [],
            intersections: [],
            segmentsMaps: [],
            segmentPolylines: [],
            segmentPolylinePoints: [],
            markers: {},
            segmentName: '',
            segmentTown: this.activity.town,
            segmentCity: this.activity.city,
            segmentCountry: this.activity.country,
        }
    },
    props: {
        activity: {
            type: Object,
            required: true,
        }
    },
    methods: {
        formatSecondsToTime(seconds) {
            return formatSecondsToTime(seconds);
        },
        formatDateTime(date){
            return formatDateTime(date);
        },
        formatSpeed(pace, activity_type, units){
            return formatSpeed(pace, activity_type, units);
        },
        highlightGate(intersectionIdx, segmentIdx, labelTxt) {
            // Find the map for this segment
            const segmentMap = this.segmentsMaps[intersectionIdx];

            for ( let i=0; i < segmentMap._gateLabels.length; i++) {
                let gateTxt = segmentMap._gateLabels[i][0];
                let label = segmentMap._gateLabels[i][1];

                if (labelTxt === segmentMap._endLabel && labelTxt === gateTxt) {
                    label.setIcon(L.divIcon({ className: 'bg-danger border border-dark rounded-circle', iconSize: [16, 16] }));
                }
                else if (labelTxt == gateTxt ){
                    label.setIcon(L.divIcon({
                        className: 'leaflet-label',
                        html: `<div style="background-color: yellow; border: 1px solid black; padding: 2px; border-radius: 5px; text-align: center;">
                                <span style="color: black; font-size: 12px; font-weight: bold;">${labelTxt}</span>
                            </div>`,
                        iconSize: new L.Point(15, 15)
                    }));
                }
            }
        },
        unhighlightGate(intersectionIdx, segmentIdx, labelTxt) {
            const segmentMap = this.segmentsMaps[intersectionIdx];

            for (let i=0; i < segmentMap._gateLabels.length; i++) {
                let gateTxt = segmentMap._gateLabels[i][0];
                let label = segmentMap._gateLabels[i][1];

                // Set normal
                if (labelTxt === segmentMap._endLabel && labelTxt === gateTxt) {
                    label.setIcon(L.divIcon({ className: 'bg-danger dot' }));
                }
                else if (labelTxt == gateTxt) {
                    label.setIcon(L.divIcon({
                        className: 'leaflet-label',
                        html: `<div style="background-color: white; border: 1px solid black; padding: 2px; border-radius: 5px; text-align: center;">
                                <span style="color: black; font-size: 12px;">${labelTxt}</span>
                            </div>`,
                        iconSize: new L.Point(15, 15)
                    }));            
                }
            }
        },
        updateSegmentIconMaps() {
            let map_idx = 0
            if (this.intersections) {
                this.intersections.forEach(intersection => {
                    setTimeout(() => {
                        // Ensure the map is rendered after the DOM is updated
                        this.createSegmentIconMap(intersection, map_idx)
                        map_idx++;
                    }, 200);
                });
            }
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
                    this.intersections =  await activitySegments.getActivitySegmentIntersections(this.activity.id);
                }
                this.updateSegmentIconMaps();
            } catch (error) {
                console.error("Failed to fetch activity segments:", error);
            }
        },
        async createSegmentIconMap(intersection, map_idx) {
            // Check if the ref for the segment map icon exists
            if (!this.$refs[`segmentMapIcon-${intersection.segment_id}-${intersection.lap_number}`]) {
                console.warn(`No ref found for segmentMapIcon-${intersection.segment_id}-${intersection.lap_number}`);
                return;
            }

            // Ensure the map container is ready
            await this.$nextTick();

            // Fetch activity stream data

            const waypoints = intersection.stream_latlon;
            const validWaypoints = waypoints.filter(waypoint => waypoint.lat && waypoint.lon);
            const latlngs = validWaypoints.map(waypoint => [waypoint.lat, waypoint.lon]);

            const gpsPointIndexOrdered = intersection.gps_point_index_ordered;
            const firstWaypointIndex = gpsPointIndexOrdered[0][1];
            const lastWaypointIndex = gpsPointIndexOrdered[gpsPointIndexOrdered.length - 1][0];

            const segmentWaypoints = validWaypoints.slice(firstWaypointIndex, lastWaypointIndex + 1);
            const segmentLatLngs = segmentWaypoints.map(waypoint => [waypoint.lat, waypoint.lon]);

            const mapCont = this.$refs[`segmentMapIcon-${intersection.segment_id}-${intersection.lap_number}`][0];

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
                opacity: 0.5
            }).addTo(segmentIconMap);

            L.polyline(segmentLatLngs, { 
                color: 'blue',
                weight: 3,
                opacity: 1
            }).addTo(segmentIconMap);

            if (!segmentIconMap._gateLabels) segmentIconMap._gateLabels = [];
            if (!segmentIconMap._endLabel) segmentIconMap._endLabel = intersection.gate_ordered.toSorted()[intersection.gate_ordered.length-1];

            for (let i=0; i < intersection.gate_ordered.length; i++) {
                const gateLabel = intersection.gate_ordered[i];
                const gps_point_idx = intersection.gps_point_index_ordered[i][0];

                const gateLatLngs = latlngs[gps_point_idx];

                var alreadyDone = false;
                for (let j=0; j < segmentIconMap._gateLabels.length; j++) {
                    if (segmentIconMap._gateLabels[j][0] == gateLabel) {
                        alreadyDone = true;
                    }
                }

                if (alreadyDone == false) {

                    // Create a label with the gate sequence number on the map
                    if (gateLabel == 0) {
                        // Create a marker for the start of the segment
                        const label = L.marker(gateLatLngs, {
                            icon: L.divIcon({ className: 'bg-success dot' })
                        }).addTo(segmentIconMap);
                        segmentIconMap._gateLabels.push([gateLabel,label]);

                    }
                    else if (gateLabel == intersection.gate_ordered[intersection.gate_ordered.length-1]) {
                        // Create a marker for the end of the segment
                        const label = L.marker(gateLatLngs, {
                            icon: L.divIcon({ className: 'bg-danger dot' })
                        }).addTo(segmentIconMap);
                        segmentIconMap._gateLabels.push([gateLabel, label]);
                    }
                    else {
                        // Create markers for the start and end of the gate
                        const label = L.marker(gateLatLngs).addTo(segmentIconMap);
                        label.setIcon(L.divIcon({
                            className: 'leaflet-label',
                            html: `<div style="background-color: white; border: 1px solid black; padding: 2px; border-radius: 5px; text-align: center;">
                                    <span style="color: black; font-size: 12px;">${gateLabel}</span>
                                </div>`,
                            iconSize: new L.Point(15, 15)
                        }));
                        segmentIconMap._gateLabels.push([gateLabel,label]);
                    }
                }
            }

            // Add the segment polyline to the map
            segmentIconMap.fitBounds(segmentLatLngs);

            segmentIconMap.on('resize', () => {
                // Ensure the map is properly sized after rendering
                segmentIconMap.fitBounds(segmentLatLngs);
            });

            this.segmentsMaps[map_idx] = segmentIconMap;
        },
        async submitSegment(){
            try {
                const gates = [];
                // Obtain and store each gate from the polyline map object to the gates array
                this.segmentPolylines.forEach(polyline => {
                    const latlngs = polyline.getLatLngs();
                    gates.push([[latlngs[0].lat, latlngs[0].lng],[latlngs[1].lat, latlngs[1].lng]]);
                });

                const data = {
                    name: this.segmentName,
                    town: this.segmentTown,
                    city: this.segmentCity,
                    country: this.segmentCountry,
                    activity_type: this.activity.activity_type,
                    gates: gates,
                };
                //console.info(data)
                this.toggleSegmentAdd();
                const submittedSegment = await activitySegments.createSegment(data);
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