<template>
    <div v-if="isLoading">
        <LoadingComponent />
    </div>
    <div v-else>
        <div class="d-flex justify-content-between">
            <!-- user name and photo zone -->
             <div class="d-flex align-items-center">
                <UserAvatarComponent :user="userSegment" :width=55 :height=55 />
                <div class="ms-3 me-3">
                    <div class="fw-bold">
                        <span v-if="userSegment">
                            <router-link :to="{ name: 'user', params: { id: userSegment.id } }"
                                class="link-body-emphasis link-underline-opacity-0
                                link-underline-opacity-100-hover">
                                {{ userSegment.name }}
                            </router-link>
                        </span>
                        <span v-else>
                            {{ $t("segmentSummaryComponent.userNameHidden") }}
                        </span>
                    </div>
                    <h6>
                        <!-- Display the visibility of the segment -->
                        <span>
                            <font-awesome-icon :icon="['fas', 'lock']" />
                                {{ $t("segmentSummaryComponent.visibilityPrivate") }}
                        </span>
                        <span> - </span>
                        <!-- Display the activity type -->
                        <span>
                            <font-awesome-icon class="me-1" :icon="getIcon(segment.activity_type)" />
                        </span>
                        <span> - </span>
                        <span v-if="segment.city || segment.town ||segment.country">
                            {{ formatSegmentLocation(segment) }}
                        </span>
                    </h6>
                </div>
             </div>
             <div class="dropdown-dflex" v-if="segment.user_id == authStore.user.id">
                <div>
                    <button class="btn btn-link btn-lg link-body-emphasis" type="button" data-bs-toggle="dropdown" aria-expanded="false">
                        <font-awesome-icon :icon="['fas', 'fa-ellipsis-vertical']" />
                    </button>
                    <ul class="dropdown-menu">
                        <!-- Add other options such as edit -->

                        <!-- Enable divider between other menu items
                        <li v-if="source === 'activity'">
                            <hr class="dropdown-divider">
                        </li>
                        -->

                        <li>
                            <a class="dropdown-item" href="#" data-bs-toggle="modal"
                                :data-bs-target="`#deleteSegmentModal${segment.id}`">
                                {{ $t("segmentSummaryComponent.buttonDeleteSegment") }}
                            </a>
                        </li>
                    </ul>
                </div>
             </div>
        </div>
        <!-- Modal's here -->
        <!-- Modal delete segment -->
        <ModalComponent :modalId="`deleteSegmentModal${segment.id}`" :title="t('segmentSummaryComponent.buttonDeleteSegment')"
            :body="`${t('segmentSummaryComponent.modalDeleteBody1')}<b>${segment.name}</b>?<br>${t('segmentSummaryComponent.modalDeleteBody2')}`"
            :actionButtonType="`danger`" :actionButtonText="t('segmentSummaryComponent.buttonDeleteSegment')" 
            @submitAction="submitDeleteSegment" />

        <!-- Segment title -->
        <h1 class="mt-3" v-if="source === 'segment'">
            <span>{{ segment.name }}</span>
        </h1>

        <!-- Segment summary -->
        <div class="row mt-3 align-items-center text-start">
            <!-- Number of times completed -->
            <div class="col">
                <span class="fw-lighter">
                    {{ $t("segmentSummaryComponent.numberOfCompletions") }}
                </span>
                <br>
                <span>{{ numTimes() }}</span>
            </div>
            <!-- Last time completed -->
            <div class="col">
                <span class="fw-lighter">
                    {{ $t("segmentSummaryComponent.lastTimeCompleted") }}
                </span>
                <br>
                <span>{{ formatDateTime(lTime[0]) }} - {{ formatSecondsToTime(lTime[1]) }}</span>
            </div>
            <!-- Fastest time -->
            <div class="col">
                <span class="fw-lighter">
                    {{ $t("segmentSummaryComponent.fastestTimeCompleted") }}
                </span>
                <br>
                <span>{{ formatDateTime(fTime[0]) }} - {{ formatSecondsToTime(fTime[1]) }}</span>
            </div>
        </div>
    </div>
</template>

<script setup>
import { ref, onMounted } from "vue";
import { useI18n } from "vue-i18n";
import { useRouter } from "vue-router";
// Importing the stores
import { useAuthStore } from "@/stores/authStore";
// Importing Notivue push
import { push } from "notivue";
// Importing the components
import LoadingComponent from "@/components/GeneralComponents/LoadingComponent.vue";
import UserAvatarComponent from "@/components/Users/UserAvatarComponent.vue";
import ModalComponent from "@/components/Modals/ModalComponent.vue";
// Importing the services
import { users } from "@/services/usersService";
import { segments } from '@/services/segmentsService';
// Importing the utils
import {
	formatDateTime,
    getIcon,
} from "@/utils/activityUtils"
import { 
    formatSegmentLocation,
    formatSecondsToTime,
 } from "@/utils/segmentUtils";

// Emits
const emit = defineEmits(["segmentDeleted"]);

// Composables
const router = useRouter();
const authStore = useAuthStore();
const { t } = useI18n();

// Reactive data
const isLoading = ref(true);
const userSegment = ref(null);
const lTime = ref(null);
const fTime = ref(null);

// Props
const props = defineProps({
    segment: {
        type: Object,
        required: true,
    },
    activitySegments: {
        type: Object,
        required: true,
    },
    source: {
        type: String,
        required: true,
    },
});

function fastestTime() {
    var starttime = '1970-01-01T00:00:00';
    var segment_time = 999999.99;
    props.activitySegments.forEach(item=> {

        if (segment_time > item.segment_times[0]) {
            starttime = item.start_time;
            segment_time = item.segment_times[0];
        };
    });
    return [starttime, segment_time];
}

function lastTime() {
    var starttime = '1970-01-01T00:00:00';
    var segment_time = 0;
    props.activitySegments.forEach(item=> {

        let prevTime = new Date(starttime);
        let itemTime = new Date(item.start_time);

        if (prevTime < itemTime) {
            starttime = item.start_time;
            segment_time = item.segment_times[0];
        };
    });
    return [starttime, segment_time];
}

function numTimes() {
    // Return the number of activitySegment records
    let count = 0;
    props.activitySegments.forEach(item=> {
        count++;
    });
    return count;
}

function numGates() {
    // Return the number of gates
    let count = 0;
    props.segment.gates.forEach(item=> {
        if (Array.isArray(item)) {
            count++;
        }
    });
    return count;
}

// Lifecycle
onMounted(async () => {
    try {
        if (authStore.isAuthenticated) {
            userSegment.value = await users.getUserById(props.segment.user_id);
            lTime.value = lastTime();
            fTime.value = fastestTime();
        }
    } catch (error) {
        push.error(`${t("segmentSummaryComponent.errorFetchingUserById")} - ${error}`);
    } finally {
        isLoading.value = false;
    }
});

// Methods
async function submitDeleteSegment(){
    try {
        userSegment.value = await segments.deleteSegment(props.segment.id);
        if (props.source === 'segment') {
            return router.push({
                path: "/segments",
                query: { segmentDeleted: "true", segmentId: props.segment.id },
            });
        }
        emit("segmentDeleted", props.segment.id);
    } catch (error) {
        push.error(`${t("segmentSummaryComponent.errorDeletingSegment")} - ${error}`);
    }
}

</script>