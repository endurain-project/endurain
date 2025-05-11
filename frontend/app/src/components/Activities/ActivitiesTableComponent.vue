<template>
  <div class="table-responsive mb-3">
    <table class="table table-striped table-hover table-sm">
      <thead>
        <tr>
          <th scope="col" class="text-center sortable-header" @click="changeSort('type')">
            {{ $t('activitiesTableComponent.headerType') }} <font-awesome-icon :icon="sortIcon('type')" class="ms-1 sort-icon" />
          </th>
          <th scope="col" class="sortable-header" @click="changeSort('name')">
            {{ $t('activitiesTableComponent.headerName') }} <font-awesome-icon :icon="sortIcon('name')" class="ms-1 sort-icon" />
          </th>
          <th scope="col" class="sortable-header" @click="changeSort('location')">
            {{ $t('activitiesTableComponent.headerLocation') }} <font-awesome-icon :icon="sortIcon('location')" class="ms-1 sort-icon" />
          </th>
          <th scope="col" class="sortable-header" @click="changeSort('start_time')">
            {{ $t('activitiesTableComponent.headerStartTime') }} <font-awesome-icon :icon="sortIcon('start_time')" class="ms-1 sort-icon" />
          </th>
          <th scope="col" class="sortable-header" @click="changeSort('duration')">
            {{ $t('activitiesTableComponent.headerDuration') }} <font-awesome-icon :icon="sortIcon('duration')" class="ms-1 sort-icon" />
          </th>
          <th scope="col" class="sortable-header" @click="changeSort('distance')">
            {{ $t('activitiesTableComponent.headerDistance') }} <font-awesome-icon :icon="sortIcon('distance')" class="ms-1 sort-icon" />
          </th>
          <th scope="col" class="sortable-header" @click="changeSort('pace')">
            {{ $t('activitiesTableComponent.headerPace') }} <font-awesome-icon :icon="sortIcon('pace')" class="ms-1 sort-icon" />
          </th>
          <th scope="col" class="sortable-header" @click="changeSort('calories')">
            {{ $t('activitiesTableComponent.headerCalories') }} <font-awesome-icon :icon="sortIcon('calories')" class="ms-1 sort-icon" />
          </th>
          <th scope="col" class="sortable-header" @click="changeSort('elevation')">
            {{ $t('activitiesTableComponent.headerElevation') }} <font-awesome-icon :icon="sortIcon('elevation')" class="ms-1 sort-icon" />
          </th>
          <th scope="col" class="sortable-header" @click="changeSort('average_hr')">
            {{ $t('activitiesTableComponent.headerAvgHr') }} <font-awesome-icon :icon="sortIcon('average_hr')" class="ms-1 sort-icon" />
          </th>
        </tr>
      </thead>
      <tbody>
        <tr v-if="activities.length === 0">
          <td colspan="10" class="text-center">{{ $t('activitiesTableComponent.noActivitiesFound') }}</td>
        </tr>
        <tr v-for="activity in activities" :key="activity.id">
          <td class="text-center">
            <font-awesome-icon :icon="getIcon(activity.activity_type)" />
          </td>
          <td>
            <router-link :to="{ name: 'activity', params: { id: activity.id } }">
              {{ activity.name }}
            </router-link>
          </td>
          <td>{{ formatLocation(activity) }}</td>
          <td>{{ formatDateTime(activity.start_time) }}</td>
          <td>{{ formatDuration(activity.total_timer_time) }}</td>
          <td>{{ formatDistance(activity.distance) }}</td>
          <td>{{ formatPace(activity, authStore.user.units) }}</td> <!-- Pass whole activity object -->
          <td>{{ formatCalories(activity.calories) }}</td>
          <td>{{ formatElevation(activity.elevation_gain) }}</td>
          <td>{{ formatAvgHr(activity.average_hr) }}</td>
        </tr>
      </tbody>
    </table>
  </div>
</template>

<script setup>
import { defineProps, defineEmits } from "vue";
import { useI18n } from "vue-i18n";
import { FontAwesomeIcon } from "@fortawesome/vue-fontawesome";
import {
	formatDuration,
	formatDateTime,
	formatDistance,
	formatElevation,
	formatPace,
	formatAvgHr,
	formatCalories,
	getIcon,
	formatLocation,
} from "@/utils/activityUtils"; // Added formatLocation
import { useAuthStore } from "@/stores/authStore";

const { t } = useI18n();
const authStore = useAuthStore();

const props = defineProps({
	activities: {
		type: Array,
		required: true,
		default: () => [],
	},
	sortBy: {
		type: String,
		default: "start_time",
	},
	sortOrder: {
		type: String,
		default: "desc",
	},
});

const emit = defineEmits(["sortChanged"]);

function changeSort(columnName) {
	emit("sortChanged", columnName);
}

function sortIcon(columnName) {
	if (props.sortBy !== columnName) {
		return ["fas", "sort"]; // Default sort icon
	}
	if (props.sortOrder === "asc") {
		return ["fas", "sort-up"]; // Ascending icon
	}
	return ["fas", "sort-down"]; // Descending icon
}
</script>

<style scoped>
.table {
  margin-bottom: 0;
}
td a {
  text-decoration: none;
}
td a:hover {
  text-decoration: underline;
}
.sortable-header {
  cursor: pointer;
}
.sortable-header:hover {
  background-color: rgba(0, 0, 0, 0.05);
}
.sort-icon {
  opacity: 0.6;
  transition: opacity 0.2s ease-in-out;
}
.sortable-header:hover .sort-icon {
  opacity: 1;
}
</style>
