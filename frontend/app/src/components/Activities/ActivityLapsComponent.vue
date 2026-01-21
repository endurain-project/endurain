<template>
  <div class="table-responsive d-none d-lg-block">
    <table
      class="table table-borderless table-hover table-sm rounded text-center"
      :class="{ 'table-striped': activity.activity_type !== 8 }"
      style="--bs-table-bg: var(--bs-gray-850)"
    >
      <thead>
        <tr>
          <th>{{ $t('activityLapsComponent.labelLapNumber') }}</th>
          <th v-if="hasIntensity">{{ $t('activityLapsComponent.labelLapIntensity') }}</th>
          <th>{{ $t('activityLapsComponent.labelLapDistance') }}</th>
          <th>{{ $t('activityLapsComponent.labelLapTime') }}</th>
          <th v-if="activityTypeIsCycling(activity)">
            {{ $t('activityLapsComponent.labelLapSpeed') }}
          </th>
          <th v-else>{{ $t('activityLapsComponent.labelLapPace') }}</th>
          <!-- Do not show elevation for swimming activities -->
          <th v-if="!activityTypeIsSwimming(activity)">
            {{ $t('activityLapsComponent.labelLapElevation') }}
          </th>
          <!-- Show Stroke Rate for swimming activities -->
          <th v-if="activityTypeIsSwimming(activity)">
            {{ $t('activityLapsComponent.labelLapStrokeRate') }}
          </th>
          <th>{{ $t('activityLapsComponent.labelLapAvgHr') }}</th>
        </tr>
      </thead>
      <tbody class="table-group-divider">
        <tr
          v-for="(lap, index) in normalizedLaps"
          :key="lap.id"
          :style="
            activity.activity_type === 8
              ? {
                  'background-color': lap.swimIsRest
                    ? 'var(--bs-table-bg)'
                    : 'var(--bs-table-striped-bg)'
                }
              : null
          "
        >
          <td>{{ index + 1 }}</td>
          <td v-if="hasIntensity">{{ lap.intensity ?? $t('generalItems.labelNoData') }}</td>
          <td>{{ lap.formattedDistance }}</td>
          <td>{{ lap.lapSecondsToMinutes }}</td>
          <td v-if="activityTypeIsCycling(activity)">{{ lap.formattedSpeedFull }}</td>
          <td v-else>{{ lap.formattedPaceFull }}</td>
          <td v-if="!activityTypeIsSwimming(activity)">{{ lap.formattedElevationFull }}</td>
          <td v-if="activityTypeIsSwimming(activity)">{{ lap.avg_cadence }}</td>
          <td>
            <span v-if="lap.avg_heart_rate">
              {{ lap.avg_heart_rate + ' ' + $t('generalItems.unitsBpm') }}
            </span>
            <span v-else>
              {{ $t('generalItems.labelNoData') }}
            </span>
          </td>
        </tr>
      </tbody>
    </table>
  </div>

  <div class="table-responsive d-lg-none d-block">
    <table class="table table-sm table-borderless" style="--bs-table-bg: var(--bs-gray-850)">
      <thead>
        <tr>
          <th scope="col" style="width: 5%">#</th>
          <th scope="col" style="width: 15%" v-if="activityTypeIsCycling(activity)">
            {{ $t('activityLapsComponent.labelLapSpeed') }}
          </th>
          <th scope="col" style="width: 15%" v-else>
            {{ $t('activityLapsComponent.labelLapPace') }}
          </th>
          <th scope="col" style="width: auto">&nbsp;</th>
          <th
            scope="col"
            style="width: 10%"
            v-if="!activityTypeIsSwimming(activity) && activityTypeNotRowing(activity)"
          >
            {{ $t('activityLapsComponent.labelLapElev') }}
          </th>
          <th scope="col" style="width: 10%" v-if="activityTypeIsSwimming(activity)">
            {{ $t('activityLapsComponent.labelLapSR') }}
          </th>
          <th scope="col" style="width: 10%">{{ $t('activityLapsComponent.labelLapHR') }}</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="(lap, index) in normalizedLaps" :key="index">
          <td>{{ index + 1 }}</td>
          <td v-if="activityTypeIsCycling(activity)">{{ lap.formattedSpeed }}</td>
          <td v-else>{{ lap.formattedPace }}</td>
          <td>
            <div
              class="progress"
              role="progressbar"
              aria-label="Basic example"
              aria-valuenow="0"
              aria-valuemin="0"
              aria-valuemax="100"
            >
              <div class="progress-bar" :style="{ width: lap.normalizedScore + '%' }"></div>
            </div>
          </td>
          <td v-if="!activityTypeIsSwimming(activity) && activityTypeNotRowing(activity)">
            {{ lap.formattedElevation }}
          </td>
          <td v-if="activityTypeIsSwimming(activity)">{{ lap.avg_cadence }}</td>
          <td>
            <span v-if="lap.avg_heart_rate">
              {{ lap.avg_heart_rate }}
            </span>
            <span v-else>
              {{ $t('generalItems.labelNotApplicable') }}
            </span>
          </td>
        </tr>
      </tbody>
    </table>
    <hr />
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
// Importing the utils
import { formatSecondsToMinutes } from '@/utils/dateTimeUtils'
import {
  formatDistance,
  formatElevation,
  formatPace,
  formatAverageSpeed,
  activityTypeIsCycling,
  activityTypeIsSwimming,
  activityTypeNotRowing
} from '@/utils/activityUtils'

// Define props
const props = defineProps({
  activity: {
    type: Object,
    required: true
  },
  activityActivityLaps: {
    type: [Object, null],
    required: true
  },
  units: {
    type: String,
    required: true
  }
})

const { t } = useI18n()

const normalizedLaps = computed(() => {
  if (!props.activityActivityLaps || props.activityActivityLaps.length === 0) {
    return []
  }

  // Extract all enhanced_avg_pace values
  const laps = props.activityActivityLaps
  const enhancedAvgPaces = laps.map((lap) => lap.enhanced_avg_pace)

  // Find the fastest pace (smallest value)
  const fastestPace = Math.min(...enhancedAvgPaces.filter((pace) => pace !== null && pace > 0))

  // Work out whether each lap is a rest (swim activities only)
  const lapsWithRest = laps.map((lap) => {
    const swimIsRest =
      activityTypeIsSwimming(props.activity) &&
      (lap.total_distance === 0 || lap.total_distance === null)
    return {
      ...lap,
      swimIsRest: swimIsRest
    }
  })
  // Assume that 2 rests in a row is an error/drills
  for (let i = 0; i < lapsWithRest.length - 1; i++) {
    if (lapsWithRest[i].swimIsRest === true && lapsWithRest[i + 1].swimIsRest === true) {
      lapsWithRest[i + 1].swimIsRest = false
    }
  }

  // Normalize each lap's pace relative to the fastest
  return lapsWithRest.map((lap) => {
    const normalizedScore = (fastestPace / lap.enhanced_avg_pace) * 100
    const formattedPace = formatPace(t, props.activity, props.units, lap, false, lap.swimIsRest)
    const formattedPaceFull = formatPace(t, props.activity, props.units, lap, true, lap.swimIsRest)
    const formattedDistance = formatDistance(t, props.activity, props.units, lap)
    const formattedElevation = formatElevation(t, lap.total_ascent, props.units, false)
    const formattedElevationFull = formatElevation(t, lap.total_ascent, props.units)
    const formattedSpeed = formatAverageSpeed(t, props.activity, props.units, lap, false)
    const formattedSpeedFull = formatAverageSpeed(t, props.activity, props.units, lap)

    return {
      ...lap,
      normalizedScore: Math.min(Math.max(normalizedScore, 0), 100), // Clamp between 0 and 100
      formattedPace: formattedPace,
      formattedPaceFull: formattedPaceFull,
      lapSecondsToMinutes: formatSecondsToMinutes(lap.total_elapsed_time),
      formattedDistance: formattedDistance,
      formattedElevation: formattedElevation,
      formattedElevationFull: formattedElevationFull,
      formattedSpeedFull: formattedSpeedFull,
      formattedSpeed: formattedSpeed
    }
  })
})

const hasIntensity = computed(() => {
  return normalizedLaps.value.some((lap) => lap.intensity !== null)
})
</script>
