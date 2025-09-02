<template>
  <div class="table-responsive" v-if="typeBreakdownData && typeBreakdownData.length">
    <table
      class="table table-borderless table-sm table-striped rounded"
      style="--bs-table-bg: var(--bs-gray-850)"
    >
      <thead>
        <tr>
          <th>{{ t('summaryView.colActivityType') }}</th>
          <th>{{ t('summaryView.colDistance') }}</th>
          <th>{{ t('summaryView.colDuration') }}</th>
          <th class="d-none d-sm-table-cell">{{ t('summaryView.colElevation') }}</th>
          <th class="d-none d-sm-table-cell">{{ t('summaryView.colCalories') }}</th>
          <th class="d-none d-md-table-cell">{{ t('summaryView.colActivities') }}</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="item in typeBreakdownData" :key="item.activity_type_id">
          <td><font-awesome-icon :icon="getIcon(item.activity_type_id)" /></td>
          <td>{{ formatRawDistance(t, item.total_distance, authStore.user.units) }}</td>
          <td>{{ formatDuration(t, item.total_duration) }}</td>
          <td class="d-none d-sm-table-cell">
            {{ formatElevation(t, item.total_elevation_gain, authStore.user.units) }}
          </td>
          <td class="d-none d-sm-table-cell">{{ formatCalories(t, item.total_calories) }}</td>
          <td class="d-none d-md-table-cell">{{ item.activity_count }}</td>
        </tr>
      </tbody>
    </table>
  </div>
  <NoItemsFoundComponents :show-shadow="false" v-else />
</template>

<script setup>
import { useI18n } from 'vue-i18n'
import { FontAwesomeIcon } from '@fortawesome/vue-fontawesome'
import NoItemsFoundComponents from '@/components/GeneralComponents/NoItemsFoundComponents.vue'
import {
  getIcon,
  formatRawDistance,
  formatDuration,
  formatElevation,
  formatCalories
} from '@/utils/activityUtils'

const props = defineProps({
  typeBreakdownData: {
    type: Array,
    required: true
  },
  authStore: {
    type: Object,
    required: true
  }
})

const { t } = useI18n()
</script>
