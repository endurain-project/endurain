<template>
    <td>
        <font-awesome-icon :icon="getIcon(activity.activity_type)"/>
    </td>
    <td>
        <router-link :to="{ name: 'activity', params: { id: activity.id } }" class="link-body-emphasis link-underline-opacity-0 link-underline-opacity-100-hover">
            {{ activity.name }}
        </router-link>
    </td>
    <td>{{ formatLocation(activity) }}</td>
    <td class="d-none d-md-table-cell">{{ formatDateTime(activity.start_time) }}</td>
    <td class="d-none d-md-table-cell">{{ formatDuration(activity.total_timer_time) }}</td>
    <td class="d-none d-md-table-cell">{{ formatDistance(activity, authStore.user.units) }}</td>
    <td class="d-none d-md-table-cell">
        <span v-if="activityTypeIsRunning(activity) || activityTypeIsSwimming(activity) || activity.activity_type === 11 || activity.activity_type === 12 || activityTypeIsRowing(activity)">
            {{ formatPace(activity, authStore.user.units) }}
        </span>
        <span v-else-if="activityTypeIsCycling(activity)">
            {{ formatAverageSpeed(activity, authStore.user.units) }}
        </span>
        <span v-else>
            {{ $t('generalItems.labelNotApplicable') }}
        </span>
    </td>
    <td class="d-none d-md-table-cell">{{ formatCalories(activity.calories) }}</td>
    <td class="d-none d-md-table-cell">{{ formatElevation(activity.elevation_gain, authStore.user.units) }}</td>
    <td class="d-none d-md-table-cell">{{ formatHr(activity.average_hr) }}</td>
</template>

<script setup>
// Importing the stores
import { useAuthStore } from "@/stores/authStore";
// Importing the utils
import {
	formatDuration,
	formatDateTime,
	formatDistance,
	formatElevation,
	formatPace,
	formatHr,
	formatCalories,
	getIcon,
	formatLocation,
    formatAverageSpeed,
    activityTypeIsCycling,
    activityTypeIsRunning,
    activityTypeIsSwimming,
    activityTypeIsRowing,
} from "@/utils/activityUtils";

// Define props
const props = defineProps({
    activity: {
        type: Object,
        required: true,
    }
});

const authStore = useAuthStore();
</script>