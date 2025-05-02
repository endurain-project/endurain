<template>
  <div class="table-responsive">
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
            <!-- Made sortable -->
            {{ $t('activitiesTableComponent.headerPace') }} <font-awesome-icon :icon="sortIcon('pace')" class="ms-1 sort-icon" />
          </th>
          <th scope="col" class="sortable-header" @click="changeSort('calories')">
            {{ $t('activitiesTableComponent.headerCalories') }} <font-awesome-icon :icon="sortIcon('calories')" class="ms-1 sort-icon" />
          </th>
          <th scope="col" class="sortable-header" @click="changeSort('elevation')">
            {{ $t('activitiesTableComponent.headerElevation') }} <font-awesome-icon :icon="sortIcon('elevation')" class="ms-1 sort-icon" />
          </th>
        </tr>
      </thead>
      <tbody>
        <tr v-if="activities.length === 0">
          <td colspan="9" class="text-center">{{ $t('activitiesTableComponent.noActivitiesFound') }}</td>
        </tr>
        <tr v-for="activity in activities" :key="activity.id">
          <td class="text-center">
            <font-awesome-icon :icon="getActivityIcon(activity.activity_type)" />
          </td>
          <td>
            <router-link :to="{ name: 'activity', params: { id: activity.id } }">
              {{ activity.name }}
            </router-link>
          </td>
          <td>
            <span v-if="activity.town || activity.city || activity.country">
              <span v-if="activity.town"
                >{{ activity.town }}<span v-if="activity.country">,</span></span
              >
              <span v-else-if="activity.city"
                >{{ activity.city }}<span v-if="activity.country">,</span></span
              >
              <span v-if="activity.country">{{ ' ' + activity.country }}</span>
            </span>
            <span v-else>{{ $t('generalItems.labelNotApplicable') }}</span>
          </td>
          <td>{{ formatDateTime(activity.start_time) }}</td>
          <td>{{ formatDuration(activity.total_timer_time) }}</td>
          <td>{{ formatDistance(activity.distance) }}</td>
          <td>{{ formatPace(activity.pace) }}</td>
          <td>{{ activity.calories ? activity.calories.toLocaleString() + ' kcal' : $t('generalItems.labelNotApplicable') }}</td>
          <td>{{ formatElevation(activity.elevation_gain) }}</td>
        </tr>
      </tbody>
    </table>
  </div>
</template>

<script setup>
import { defineProps, defineEmits, computed } from 'vue'
import { useI18n } from 'vue-i18n' // Import useI18n
import { FontAwesomeIcon } from '@fortawesome/vue-fontawesome'

const { t } = useI18n() // Setup useI18n

const props = defineProps({
  activities: {
    type: Array,
    required: true,
    default: () => []
  },
  sortBy: {
    type: String,
    default: 'start_time'
  },
  sortOrder: {
    type: String,
    default: 'desc'
  }
})

const emit = defineEmits(['sort-changed'])

function changeSort(columnName) {
  emit('sort-changed', columnName)
}

const sortIcon = computed(() => (columnName) => {
  if (props.sortBy !== columnName) {
    return ['fas', 'sort'] // Default sort icon
  }
  if (props.sortOrder === 'asc') {
    return ['fas', 'sort-up'] // Ascending icon
  }
  return ['fas', 'sort-down'] // Descending icon
})

function formatDateTime(dateTimeString) {
  if (!dateTimeString) return t('generalItems.labelNotApplicable')
  try {
    const options = {
      year: 'numeric',
      month: 'short',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit'
    }
    return new Date(dateTimeString).toLocaleString(undefined, options)
  } catch (e) {
    console.error('Error formatting date:', e)
    return dateTimeString // Fallback
  }
}

function formatDuration(seconds) {
  if (seconds === null || seconds === undefined) return t('generalItems.labelNotApplicable')
  const h = Math.floor(seconds / 3600)
  const m = Math.floor((seconds % 3600) / 60)
  const s = Math.floor(seconds % 60)
  let result = ''
  if (h > 0) result += `${h}h `
  if (m > 0 || h > 0) result += `${m}m ` // Show minutes if hours exist
  result += `${s}s`
  return result.trim()
}

function formatDistance(meters) {
  if (meters === null || meters === undefined) return t('generalItems.labelNotApplicable')
  const kilometers = meters / 1000
  const precision = kilometers < 10 ? 2 : 1
  return `${kilometers.toFixed(precision)} km` // Assuming 'km' unit doesn't need translation for US
}

function formatPace(pace) {
  if (pace === null || pace === undefined || pace <= 0) return t('generalItems.labelNotApplicable')

  // Convert seconds/meter to seconds/kilometer
  const paceSecondsPerKm = pace * 1000

  const minutes = Math.floor(paceSecondsPerKm / 60)
  const seconds = Math.round(paceSecondsPerKm % 60)
  return `${minutes}:${seconds.toString().padStart(2, '0')} /km`
}

function formatElevation(meters) {
  if (meters === null || meters === undefined) return t('generalItems.labelNotApplicable')
  return `${meters.toLocaleString()} m` // Assuming 'm' unit doesn't need translation for US
}

function getActivityIcon(typeId) {
  // Based on logic in ActivitySummaryComponent.vue
  if (typeId == 1 || typeId == 2) {
    return ['fas', 'person-running']
  } else if (typeId == 3) {
    return ['fas', 'person-running'] // Consider a different icon for virtual?
  } else if (typeId == 4 || typeId == 5 || typeId == 6 || typeId == 27) {
    return ['fas', 'person-biking']
  } else if (typeId == 7) {
    return ['fas', 'person-biking'] // Consider a different icon for virtual?
  } else if (typeId == 8 || typeId == 9) {
    return ['fas', 'person-swimming']
  } else if (typeId == 11) {
    return ['fas', 'person-walking']
  } else if (typeId == 12) {
    return ['fas', 'person-hiking']
  } else if (typeId == 13) {
    return ['fas', 'sailboat'] // Rowing icon might be better if available
  } else if (typeId == 14) {
    return ['fas', 'hands-praying'] // Yoga icon might be better if available
  } else if (typeId == 15) {
    return ['fas', 'person-skiing']
  } else if (typeId == 16) {
    return ['fas', 'person-skiing-nordic']
  } else if (typeId == 17) {
    return ['fas', 'person-snowboarding']
  } else if (typeId == 18) {
    return ['fas', 'repeat'] // Transition icon
  } else if (
    typeId == 21 ||
    typeId == 22 ||
    typeId == 23 ||
    typeId == 24 ||
    typeId == 25 ||
    typeId == 26
  ) {
    return ['fas', 'table-tennis-paddle-ball'] // Racquet sports
  } else {
    // Default for Workout, Strength, Crossfit, etc.
    return ['fas', 'dumbbell']
  }
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
