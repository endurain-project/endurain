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
        <span v-if="activity.activity_type === 1 || activity.activity_type === 2 || activity.activity_type === 3 || activity.activity_type === 8 || activity.activity_type === 9 || activity.activity_type === 11 || activity.activity_type === 12 || activity.activity_type === 13">
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

<script>
import { useI18n } from "vue-i18n";
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
} from "@/utils/activityUtils";

export default {
	props: {
		activity: {
			type: Object,
			required: true,
		},
	},
	setup(props) {
		const { t } = useI18n();
		const authStore = useAuthStore();

		return {
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
			t,
			authStore,
		};
	},
};
</script>