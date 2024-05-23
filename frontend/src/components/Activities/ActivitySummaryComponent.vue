<template>
    <!-- Error alerts -->
    <ErrorToastComponent v-if="errorMessage" />

    <div v-if="isLoading">
        <LoadingComponent />
    </div>
    <div v-else>
        <div class="d-flex justify-content-between">
            <!-- user name and photo zone -->
            <div class="d-flex align-items-center" v-if="userActivity">
                <UserAvatarComponent :userProp="userActivity" :width=55 :height=55 />
                <div class="ms-3 me-3">
                    <div class="fw-bold">
                        <router-link :to="{ name: 'activity', params: { id: activity.id }}" class="link-body-emphasis link-underline-opacity-0 link-underline-opacity-100-hover" v-if="sourceProp === 'home'">
                            {{ activity.name}}
                        </router-link>
                        <router-link :to="{ name: 'user', params: { id: userActivity.id }}" class="link-body-emphasis link-underline-opacity-0 link-underline-opacity-100-hover" v-if="sourceProp === 'activity'">
                            {{ userActivity.name}}
                        </router-link>
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
            <div class="dropdown d-flex">
                <a class="btn btn-link btn-lg mt-1 link-body-emphasis" :href="`https://www.strava.com/activities/${activity.strava_activity_id}`" role="button" v-if="activity.strava_activity_id">
                    <font-awesome-icon :icon="['fab', 'fa-strava']" />
                </a>
                <div v-if="sourceProp === 'activity'">
                    <button class="btn btn-link btn-lg link-body-emphasis" type="button" data-bs-toggle="dropdown" aria-expanded="false">
                        <font-awesome-icon :icon="['fas', 'fa-ellipsis-vertical']" />
                    </button>
                    <ul class="dropdown-menu">
                        <li>
                            <a class="dropdown-item" :class="{ disabled: activity.strava_activity_id }" href="#" data-bs-toggle="modal" data-bs-target="#deleteActivityModal">
                                {{ $t("activitySummary.buttonDeleteActivity") }}
                            </a>
                        </li>
                    </ul>
                </div>
            </div>
        </div>

        <!-- Modal delete gear -->
        <div class="modal fade" id="deleteActivityModal" tabindex="-1" aria-labelledby="deleteActivityModal"
            aria-hidden="true">
            <div class="modal-dialog">
                <div class="modal-content">
                    <div class="modal-header">
                        <h1 class="modal-title fs-5" id="deleteActivityModal">
                            {{ $t("activitySummary.buttonDeleteActivity") }}
                        </h1>
                        <button type="button" class="btn-close" data-bs-dismiss="modal" aria-label="Close"></button>
                    </div>
                    <div class="modal-body">
                        <span>{{ $t("activitySummary.modalDeleteBody1") }}<b>{{ activity.name }}</b>?</span>
                        <br>
                        <span>{{ $t("activitySummary.modalDeleteBody2") }}</span>
                    </div>
                    <div class="modal-footer">
                        <button type="button" class="btn btn-secondary" data-bs-dismiss="modal">
                            {{ $t("generalItens.buttonClose") }}
                        </button>
                        <a @click="submitDeleteActivity" type="button" class="btn btn-danger" data-bs-dismiss="modal">
                            {{ $t("activitySummary.buttonDeleteActivity") }}
                        </a>
                    </div>
                </div>
            </div>
        </div>

        <!-- Activity title -->
        <h1 class="mt-3" v-if="sourceProp === 'activity'">
            {{ activity.name }}
        </h1>
        <!-- Activity summary -->
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
        <div class="row d-flex mt-3" v-if="sourceProp === 'activity'">
            <div class="col" v-if="activity.activity_type == 1 || activity.activity_type == 2 || activity.activity_type == 3">
                <span class="fw-lighter">
                    {{ $t("activitySummary.activityAvgPower") }}
                </span>
                <br>
                <span v-if="activity.average_power">{{ activity.average_power }} W</span>
                <span v-else>{{ $t("activitySummary.activityNoData") }}</span>
            </div>
            <div class="col border-start border-opacity-50" v-if="activity.activity_type == 1 || activity.activity_type == 2 || activity.activity_type == 3">
                <span class="fw-lighter">{{ $t("activitySummary.activityEleGain") }}</span>
                <br>
                <span>{{ activity.elevation_gain }} m</span>
            </div>
            <div class="col border-start border-opacity-50" v-if="activity.activity_type == 1 || activity.activity_type == 2 || activity.activity_type == 3">
                <span class="fw-lighter">
                    {{ $t("activitySummary.activityEleLoss") }}
                </span>
                <br>
                <span>{{ activity.elevation_loss }} m</span>
            </div>
            <div class="col" v-if="activity.activity_type == 4 || activity.activity_type == 5 || activity.activity_type == 6">
                <span class="fw-lighter">{{ $t("activitySummary.activityAvgSpeed") }}</span>
                <br>
                <span>{{ (activity.average_speed * 3.6).toFixed(0) }} km/h</span>
            </div>
            <div class="col border-start border-opacity-50" v-if="activity.activity_type == 4 || activity.activity_type == 5 || activity.activity_type == 6">
                <span class="fw-lighter">
                    {{ $t("activitySummary.activityAvgPower") }}
                </span>
                <br>
                <span v-if="activity.average_power">{{ activity.average_power }} W</span>
                <span v-else>{{ $t("activitySummary.activityNoData") }}</span>
            </div>
            <div class="col border-start border-opacity-50" v-if="activity.activity_type == 4 || activity.activity_type == 5 || activity.activity_type == 6">
                <span class="fw-lighter">{{ $t("activitySummary.activityEleLoss") }}</span>
                <br>
                <span>{{ activity.elevation_loss }} m</span>
            </div>
        </div>
    </div>
</template>

<script>
import { ref, onMounted, watchEffect, computed } from 'vue';
import { useI18n } from 'vue-i18n';
import { useRouter } from 'vue-router';
// Importing the components
import LoadingComponent from '@/components/LoadingComponent.vue';
import ErrorToastComponent from '@/components/Toasts/ErrorToastComponent.vue';
import UserAvatarComponent from '@/components/Users/UserAvatarComponent.vue';
// Importing the stores
import { useErrorAlertStore } from '@/stores/Alerts/errorAlert';
// Importing the services
import { users } from '@/services/user';
import { activities } from '@/services/activities';
import { formatDate, formatTime, calculateTimeDifference } from '@/utils/dateTimeUtils';
import { formatPace } from '@/utils/activityUtils';

export default {
    components: {
        LoadingComponent,
        ErrorToastComponent,
        UserAvatarComponent,
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
        const router = useRouter();
        const { t } = useI18n();
        const isLoading = ref(true);
        const errorMessage = ref('');
        const userActivity = ref(null);
        const formattedPace = computed(() => formatPace(props.activity.pace));
        const sourceProp = ref(props.source);
        const errorAlertStore = useErrorAlertStore();

        onMounted(async () => {
            try {
                userActivity.value = await users.getUserById(props.activity.user_id);
            } catch (error) {
                console.error("Failed to fetch activity details:", error);
            } finally {
                isLoading.value = false;
            }
        });

        watchEffect(() => {
            
        });

        async function submitDeleteActivity() {
            try {
                userActivity.value = await activities.deleteActivity(props.activity.id);
                router.push({ path: '/', query: { activityDeleted: 'true', activityId: props.activity.id } });
            } catch (error) {
                errorMessage.value = t('generalItens.errorDeletingInfo') + " - " + error.toString();
                errorAlertStore.setAlertMessage(errorMessage.value);
            }
        }

        return {
            isLoading,
            t,
            userActivity,
            formatDate,
            formatTime,
            calculateTimeDifference,
            formattedPace,
            sourceProp,
            submitDeleteActivity,
            errorMessage,
        };
    },
};
</script>