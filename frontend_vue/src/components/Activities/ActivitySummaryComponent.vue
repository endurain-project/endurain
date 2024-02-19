<template>
    <div class="card">
        <div class="card-body">
            <div v-if="isLoading">
                <LoadingComponent />
            </div>
            <div v-else>
                <div class="d-flex justify-content-between">
                    <!-- user name and photo zone -->
                    <div class="d-flex align-items-center">
                        <img :src="userActivity.photo_path" alt="User Photo" width="55" height="55" class="rounded-circle" v-if="userActivity.photo_path">
                        <img src="/src/assets/avatar/male1.png" alt="Default Male Avatar" width="55" height="55" class="rounded-circle" v-else-if="!userActivity.photo_path && userActivity.gender == 1">
                        <img src="/src/assets/avatar/female1.png" alt="Default Female Avatar" width="55" height="55" class="rounded-circle" v-else>
                        <div class="ms-3 me-3">
                            <div class="fw-bold">
                                <a href="#" class="link-underline-opacity-25 link-underline-opacity-100-hover">
                                    {{ activity.name }}
                                </a>
                            </div>
                            <h6>
                                <span v-if="activity.activity_type == 1 || activity.activity_type == 2">
                                    <font-awesome-icon :icon="['fas', 'person-running']" />
                                </span>
                                <span v-else-if="activity.activity_type == 3">
                                    <font-awesome-icon :icon="['fas', 'person-running']" /> (Virtual)
                                </span>
                                <span v-else-if="activity.activity_type == 4 || activity.activity_type == 5 || activity.activity_type == 6">
                                    <font-awesome-icon :icon="['fas', 'fa-person-biking']" />
                                </span>
                                <span v-else-if="activity.activity_type == 7">
                                    <font-awesome-icon :icon="['fas', 'fa-person-biking']" /> (Virtual)
                                </span>
                                <span v-else-if="activity.activity_type == 8 || activity.activity_type == 9">
                                    <font-awesome-icon :icon="['fas', 'fa-person-swimming']" />
                                </span>
                                <span v-else>
                                    <font-awesome-icon :icon="['fas', 'fa-dumbbell']" />
                                </span>
                                <span>{{ " " + formatDate(activity.start_time) }}</span> @
                                <span>{{ formatTime(activity.start_time) }}</span>
                                <!-- Conditionally display city and country -->
                                <span v-if="activity.city || activity.country">
                                    - 
                                    <span v-if="activity.town">{{ activity.town }},</span>
                                    <span v-if="activity.country">{{ " " + activity.country }}</span>
                                </span>
                            </h6>
                        </div>
                    </div>
                    <div class="dropdown d-flex" v-if="activity.strava_activity_id">
                        <a class="btn btn-link btn-lg mt-1" :href="`https://www.strava.com/activities/${activity.strava_activity_id}`" role="button">
                            <font-awesome-icon :icon="['fab', 'fa-strava']" />
                        </a>
                    </div>
                </div>
                <div class="row d-flex mt-3">
                    <div class="col">
                        <span class="fw-lighter">
                            {{ $t("activitySummary.activityDistance") }}
                        </span>
                        <br>
                        <span>
                            <!-- Check if activity_type is not 9 -->
                            {{ activity.activity_type != 9 
                                ? (activity.distance / 1000).toFixed(2) + ' km' : activity.distance + ' m'
                            }}
                        </span>
                    </div>
                    <div class="col border-start border-opacity-50">
                        <span class="fw-lighter">
                            {{ $t("activitySummary.activityTime") }}
                        </span>
                        <br>
                        <span>{{ calculateTimeDifference(activity.start_time, activity.end_time) }}</span>
                    </div>
                    <div class="col border-start border-opacity-50">
                        <div v-if="activity.activity_type != 9 && activity.activity_type != 1">
                            <span class="fw-lighter">
                                {{ $t("activitySummary.activityElevationGain") }}
                            </span>
                            <br>
                            <span>{{ activity.elevation_gain }} m</span>
                        </div>
                        <div v-else-if="activity.activity_type == 1 || activity.activity_type == 2 || activity.activity_type == 3 || activity.activity_type == 9">
                            <span class="fw-lighter">
                                {{ $t("activitySummary.activityPace") }}
                            </span>
                            <br>
                            {{ formattedPace }}
                        </div>
                    </div>
                </div>
            </div>
        </div>
        <!-- map zone -->
        <div class="mx-3 mb-3" v-if="isLoading">
            <LoadingComponent />
        </div>
        <div class="mx-3 mb-3" v-else>
            <div ref="activityMap" class="map" style="height: 300px;"></div>
        </div>
    </div>
    <br>
</template>

<script>
import { ref, onMounted, watchEffect, computed, nextTick } from 'vue';
import { users } from '@/services/user';
import { activityStreams } from '@/services/activityStreams';
import LoadingComponent from '@/components/LoadingComponent.vue';
import { formatDate, formatTime, calculateTimeDifference } from '@/utils/dateTimeUtils';
import { formatPace } from '@/utils/activityUtils';
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
    },
    setup(props) {
        const isLoading = ref(true);
        const userActivity = ref(null);
        const activityStreamLatLng = ref(null);
        const formattedPace = computed(() => formatPace(props.activity.pace));
        const activityMap = ref(null);

        onMounted(async () => {
            try {
                userActivity.value = await users.getUserById(props.activity.user_id);
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
            
            const map = L.map(activityMap.value, {
                dragging: false, // Disable panning
                touchZoom: false, // Disable touch zoom
                scrollWheelZoom: false, // Disable scroll wheel zoom
                zoomControl: false // Remove zoom control buttons
            }).fitWorld();

            L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
                attribution: '© OpenStreetMap contributors'
            }).addTo(map);

            const latlngs = waypoints.map(waypoint => [waypoint.lat, waypoint.lon]);
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
            userActivity,
            activityStreamLatLng,
            formatDate,
            formatTime,
            calculateTimeDifference,
            formattedPace,
            activityMap,
        };
    },
};
</script>