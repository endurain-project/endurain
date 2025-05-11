<template>
  <div class="table-responsive mb-3">
    <table class="table table-striped table-hover table-sm">
      <thead>
        <tr>
          <th scope="col" class="text-center user-select-none" style="cursor: pointer;" @click="changeSort('type')">
            <span class="d-flex align-items-center justify-content-center">
              {{ $t('activitiesTableComponent.headerType') }} 
              <font-awesome-icon :icon="sortIcon('type')" class="ms-1 opacity-75" />
            </span>
          </th>
          <th scope="col" class="user-select-none" style="cursor: pointer;" @click="changeSort('name')">
            <span class="d-flex align-items-center">
              {{ $t('activitiesTableComponent.headerName') }}
              <font-awesome-icon :icon="sortIcon('name')" class="ms-1 opacity-75" />
            </span>
          </th>
          <th scope="col" class="user-select-none" style="cursor: pointer;" @click="changeSort('location')">
            <span class="d-flex align-items-center">
              {{ $t('activitiesTableComponent.headerLocation') }}
              <font-awesome-icon :icon="sortIcon('location')" class="ms-1 opacity-75" />
            </span>
          </th>
          <th scope="col" class="user-select-none d-none d-md-table-cell" style="cursor: pointer;" @click="changeSort('start_time')">
            <span class="d-flex align-items-center">
              {{ $t('activitiesTableComponent.headerStartTime') }}
              <font-awesome-icon :icon="sortIcon('start_time')" class="ms-1 opacity-75" />
            </span>
          </th>
          <th scope="col" class="user-select-none d-none d-md-table-cell" style="cursor: pointer;" @click="changeSort('duration')">
            <span class="d-flex align-items-center">
              {{ $t('activitiesTableComponent.headerDuration') }}
              <font-awesome-icon :icon="sortIcon('duration')" class="ms-1 opacity-75" />
            </span>
          </th>
          <th scope="col" class="user-select-none d-none d-md-table-cell" style="cursor: pointer;" @click="changeSort('distance')">
            <span class="d-flex align-items-center">
              {{ $t('activitiesTableComponent.headerDistance') }}
              <font-awesome-icon :icon="sortIcon('distance')" class="ms-1 opacity-75" />
            </span>
          </th>
          <th scope="col" class="user-select-none d-none d-md-table-cell" style="cursor: pointer;" @click="changeSort('pace')">
            <span class="d-flex align-items-center">
              {{ $t('activitiesTableComponent.headerPace') }}
              <font-awesome-icon :icon="sortIcon('pace')" class="ms-1 opacity-75" />
            </span>
          </th>
          <th scope="col" class="user-select-none d-none d-md-table-cell" style="cursor: pointer;" @click="changeSort('calories')">
            <span class="d-flex align-items-center">
              {{ $t('activitiesTableComponent.headerCalories') }}
              <font-awesome-icon :icon="sortIcon('calories')" class="ms-1 opacity-75" />
            </span>
          </th>
          <th scope="col" class="user-select-none d-none d-md-table-cell" style="cursor: pointer;" @click="changeSort('elevation')">
            <span class="d-flex align-items-center">
              {{ $t('activitiesTableComponent.headerElevation') }}
              <font-awesome-icon :icon="sortIcon('elevation')" class="ms-1 opacity-75" />
            </span>
          </th>
          <th scope="col" class="user-select-none d-none d-md-table-cell" style="cursor: pointer;" @click="changeSort('average_hr')">
            <span class="d-flex align-items-center">
              {{ $t('activitiesTableComponent.headerAvgHr') }}
              <font-awesome-icon :icon="sortIcon('average_hr')" class="ms-1 opacity-75" />
            </span>
          </th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="activity in activities" :key="activity.id">
          <td class="text-center">
            <font-awesome-icon :icon="getIcon(activity.activity_type)" />
          </td>
          <td>
            <router-link :to="{ name: 'activity', params: { id: activity.id } }" class="link-body-emphasis link-underline-opacity-0 link-underline-opacity-100-hover">
              {{ activity.name }}
            </router-link>
          </td>
          <td>{{ formatLocation(activity) }}</td>
          <td class="d-none d-md-table-cell">{{ formatDateTime(activity.start_time) }}</td>
          <td class="d-none d-md-table-cell">{{ formatDuration(activity.total_timer_time) }}</td>
          <td class="d-none d-md-table-cell">{{ formatDistance(activity.distance) }}</td>
          <td class="d-none d-md-table-cell">{{ formatPace(activity, authStore.user.units) }}</td>
          <td class="d-none d-md-table-cell">{{ formatCalories(activity.calories) }}</td>
          <td class="d-none d-md-table-cell">{{ formatElevation(activity.elevation_gain) }}</td>
          <td class="d-none d-md-table-cell">{{ formatAvgHr(activity.average_hr) }}</td>
        </tr>
      </tbody>
    </table>
  </div>
</template>

<script>
import { useI18n } from "vue-i18n";
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
} from "@/utils/activityUtils";
import { useAuthStore } from "@/stores/authStore";

export default {
	props: {
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
	},
	emits: ["sortChanged"],
	setup(props, { emit }) {
		const { t } = useI18n();
		const authStore = useAuthStore();

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

		return {
			formatDuration,
			formatDateTime,
			formatDistance,
			formatElevation,
			formatPace,
			formatAvgHr,
			formatCalories,
			getIcon,
			formatLocation,
			t,
			authStore,
			changeSort,
			sortIcon,
		};
	},
};
</script>