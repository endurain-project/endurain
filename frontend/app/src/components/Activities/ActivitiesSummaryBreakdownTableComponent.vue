<template>
  <div class="table-responsive">
    <table
      class="table table-borderless table-sm table-striped rounded"
      style="--bs-table-bg: var(--bs-gray-850)"
    >
      <thead>
        <tr>
          <th>{{ breakdownHeader }}</th>
          <th>{{ t('summaryView.colDistance') }}</th>
          <th>{{ t('summaryView.colDuration') }}</th>
          <th class="d-none d-sm-table-cell">{{ t('summaryView.colElevation') }}</th>
          <th class="d-none d-sm-table-cell">{{ t('summaryView.colCalories') }}</th>
          <th class="d-none d-md-table-cell">{{ t('summaryView.colActivities') }}</th>
        </tr>
      </thead>
      <tbody>
        <tr
          v-for="(item, index) in summaryData.breakdown"
          :key="`${selectedViewType}-${getBreakdownKey(item)}-${index}`"
        >
          <td>{{ getBreakdownLabel(item) }}</td>
          <td>{{ formatRawDistance(t, item.total_distance, authStore.user.units) }}</td>
          <td>{{ formatDuration(t, item.total_duration) }}</td>
          <td class="d-none d-sm-table-cell">
            {{ formatElevation(t, item.total_elevation_gain, authStore.user.units) }}
          </td>
          <td class="d-none d-sm-table-cell">{{ formatCalories(t, item.total_calories) }}</td>
          <td class="d-none d-md-table-cell">{{ item.activity_count }}</td>
        </tr>
        <tr v-if="!summaryData.breakdown || summaryData.breakdown.length === 0">
          <td colspan="6" class="text-center">{{ t('summaryView.noDataForPeriod') }}</td>
        </tr>
      </tbody>
    </table>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import {
  formatRawDistance,
  formatDuration,
  formatElevation,
  formatCalories
} from '@/utils/activityUtils'

const props = defineProps({
  selectedViewType: {
    type: String,
    required: true
  },
  summaryData: {
    type: Object,
    required: true
  },
  authStore: {
    type: Object,
    required: true
  },
  selectedYear: {
    type: Number,
    required: true
  }
})

const { t } = useI18n()

const BREAKDOWN_KEY_MAP = {
  week: (item) => item.day_of_week,
  month: (item) => item.week_number,
  year: (item) => item.month_number,
  lifetime: (item) => item.year_number
}

const getBreakdownKey = (item) => {
  const keyFn = BREAKDOWN_KEY_MAP[props.selectedViewType]
  return keyFn ? keyFn(item) : ''
}

const DAYS_OF_WEEK = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']

const BREAKDOWN_LABEL_MAP = {
  week: (item) => DAYS_OF_WEEK[item.day_of_week] || 'Unknown Day',
  month: (item) => `${t('summaryView.colWeekNum')} ${item.week_number}`,
  year: (item) => {
    const monthDate = new Date(Date.UTC(props.selectedYear, item.month_number - 1, 1))
    return monthDate.toLocaleDateString(undefined, {
      month: 'long',
      timeZone: 'UTC'
    })
  },
  lifetime: (item) => item.year_number
}

const getBreakdownLabel = (item) => {
  const labelFn = BREAKDOWN_LABEL_MAP[props.selectedViewType]
  return labelFn ? labelFn(item) : ''
}

const BREAKDOWN_HEADERS = {
  week: () => t('summaryView.colDay'),
  month: () => t('summaryView.colWeekNum'),
  year: () => t('summaryView.colMonth'),
  lifetime: () => t('summaryView.colYear')
}

const breakdownHeader = computed(() => {
  const headerFn = BREAKDOWN_HEADERS[props.selectedViewType]
  return headerFn ? headerFn() : 'Period'
})
</script>
