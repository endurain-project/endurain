<template>
  <div class="table-responsive mb-3">
    <table
      class="table table-borderless table-striped table-hover table-sm rounded"
      style="--bs-table-bg: var(--bs-gray-850)"
    >
      <thead>
        <tr>
          <th style="cursor: pointer; white-space: nowrap" @click="changeSort('type')">
            <span class="d-flex align-items-center flex-nowrap">
              {{ $t('activitiesTableComponent.headerType') }}
              <font-awesome-icon :icon="sortIcon('type')" class="ms-1 opacity-75" />
            </span>
          </th>
          <th style="cursor: pointer; white-space: nowrap" @click="changeSort('name')">
            <span class="d-flex align-items-center flex-nowrap">
              {{ $t('activitiesTableComponent.headerName') }}
              <font-awesome-icon :icon="sortIcon('name')" class="ms-1 opacity-75" />
            </span>
          </th>
          <th style="cursor: pointer; white-space: nowrap" @click="changeSort('location')">
            <span class="d-flex align-items-center flex-nowrap">
              {{ $t('activitiesTableComponent.headerLocation') }}
              <font-awesome-icon :icon="sortIcon('location')" class="ms-1 opacity-75" />
            </span>
          </th>
          <th
            class="d-none d-md-table-cell"
            style="cursor: pointer; white-space: nowrap"
            @click="changeSort('start_time')"
          >
            <span class="d-flex align-items-center flex-nowrap">
              {{ $t('activitiesTableComponent.headerStartTime') }}
              <font-awesome-icon :icon="sortIcon('start_time')" class="ms-1 opacity-75" />
            </span>
          </th>
          <th
            class="d-none d-md-table-cell"
            style="cursor: pointer; white-space: nowrap"
            @click="changeSort('duration')"
          >
            <span class="d-flex align-items-center flex-nowrap">
              {{ $t('activitiesTableComponent.headerDuration') }}
              <font-awesome-icon :icon="sortIcon('duration')" class="ms-1 opacity-75" />
            </span>
          </th>
          <th
            class="d-none d-md-table-cell"
            style="cursor: pointer; white-space: nowrap"
            @click="changeSort('distance')"
          >
            <span class="d-flex align-items-center flex-nowrap">
              {{ $t('activitiesTableComponent.headerDistance') }}
              <font-awesome-icon :icon="sortIcon('distance')" class="ms-1 opacity-75" />
            </span>
          </th>
          <th
            class="d-none d-md-table-cell"
            style="cursor: pointer; white-space: nowrap"
            @click="changeSort('pace')"
          >
            <span class="d-flex align-items-center flex-nowrap">
              {{ $t('activitiesTableComponent.headerPace') }}
              <font-awesome-icon :icon="sortIcon('pace')" class="ms-1 opacity-75" />
            </span>
          </th>
          <th
            class="d-none d-md-table-cell"
            style="cursor: pointer; white-space: nowrap"
            @click="changeSort('calories')"
          >
            <span class="d-flex align-items-center flex-nowrap">
              {{ $t('activitiesTableComponent.headerCalories') }}
              <font-awesome-icon :icon="sortIcon('calories')" class="ms-1 opacity-75" />
            </span>
          </th>
          <th
            class="d-none d-md-table-cell"
            style="cursor: pointer; white-space: nowrap"
            @click="changeSort('elevation')"
          >
            <span class="d-flex align-items-center flex-nowrap">
              {{ $t('activitiesTableComponent.headerElevation') }}
              <font-awesome-icon :icon="sortIcon('elevation')" class="ms-1 opacity-75" />
            </span>
          </th>
          <th
            class="d-none d-md-table-cell"
            style="cursor: pointer; white-space: nowrap"
            @click="changeSort('average_hr')"
          >
            <span class="d-flex align-items-center flex-nowrap">
              {{ $t('activitiesTableComponent.headerAvgHr') }}
              <font-awesome-icon :icon="sortIcon('average_hr')" class="ms-1 opacity-75" />
            </span>
          </th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="activity in activities" :key="activity.id">
          <ActivitiesTableRowComponent :activity="activity" />
        </tr>
      </tbody>
    </table>
  </div>
</template>

<script>
import { useI18n } from 'vue-i18n'
// Importing the components
import ActivitiesTableRowComponent from './ActivitiesTableRowComponent.vue'

export default {
  components: {
    ActivitiesTableRowComponent
  },
  props: {
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
  },
  emits: ['sortChanged'],
  setup(props, { emit }) {
    const { t } = useI18n()

    function changeSort(columnName) {
      emit('sortChanged', columnName)
    }

    function sortIcon(columnName) {
      if (props.sortBy !== columnName) {
        return ['fas', 'sort'] // Default sort icon
      }
      if (props.sortOrder === 'asc') {
        return ['fas', 'sort-up'] // Ascending icon
      }
      return ['fas', 'sort-down'] // Descending icon
    }

    return {
      t,
      changeSort,
      sortIcon
    }
  }
}
</script>
