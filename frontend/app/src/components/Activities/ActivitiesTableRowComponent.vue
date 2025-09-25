<template>
  <td>
    <font-awesome-icon :icon="getIcon(activity.activity_type)" />
  </td>
  <td>
    <router-link
      :to="{ name: 'activity', params: { id: activity.id } }"
      class="link-body-emphasis link-underline-opacity-0 link-underline-opacity-100-hover"
    >
      <span v-if="activity.name === 'Workout'">{{ formatName(activity, t) }}</span>
      <span v-else>{{ activity.name }}</span>
    </router-link>
  </td>
  <td>{{ formatLocation(t, activity) }}</td>
  <td class="d-none d-md-table-cell">{{ formatDateTime(t, activity.start_time_tz_applied) }}</td>
  <td class="d-none d-md-table-cell">{{ formatDuration(t, activity.total_timer_time) }}</td>
  <td class="d-none d-md-table-cell">{{ formatDistance(t, activity, authStore.user.units) }}</td>
  <td class="d-none d-md-table-cell">
    <span
      v-if="
        activityTypeIsRunning(activity) ||
        activityTypeIsSwimming(activity) ||
        activityTypeIsWalking(activity) ||
        activityTypeIsRowing(activity)
      "
    >
      {{ formatPace(t, activity, authStore.user.units) }}
    </span>
    <span v-else-if="activityTypeIsCycling(activity)">
      {{ formatAverageSpeed(t, activity, authStore.user.units) }}
    </span>
    <span v-else>
      {{ $t('generalItems.labelNotApplicable') }}
    </span>
  </td>
  <td class="d-none d-md-table-cell">{{ formatCalories(t, activity.calories) }}</td>
  <td class="d-none d-md-table-cell">
    {{ formatElevation(t, activity.elevation_gain, authStore.user.units) }}
  </td>
  <td class="d-none d-md-table-cell">{{ formatHr(t, activity.average_hr) }}</td>
</template>

<script setup>
// Importing the stores
import { useAuthStore } from '@/stores/authStore'
import { useI18n } from 'vue-i18n'
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
  activityTypeIsWalking,
  activityTypeIsCycling,
  activityTypeIsRunning,
  activityTypeIsSwimming,
  activityTypeIsRowing,
  formatName
} from '@/utils/activityUtils'

// Define props
const props = defineProps({
  activity: {
    type: Object,
    required: true
  }
})

const authStore = useAuthStore()
const { t } = useI18n()
</script>
