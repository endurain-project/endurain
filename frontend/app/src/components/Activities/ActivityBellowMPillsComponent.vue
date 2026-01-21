<template>
  <div if="activity" class="fw-lighter">
    <!-- laps -->
    <ActivityLapsComponent
      :activity="activity"
      :activityActivityLaps="activityActivityLaps"
      :units="units"
      v-if="activityActivityLaps && activityActivityLaps.length > 0"
    />

    <!-- Pace values -->
    <div v-if="pacePresent">
      <span class="fw-normal">
        {{ $t('activityBellowMPillsComponent.subTitlePace') }}
      </span>
      <ActivityStreamsLineChartComponent
        :activity="activity"
        :graphSelection="'pace'"
        :activityStreams="activityActivityStreams"
      />
      <div class="d-flex justify-content-between mt-3" v-if="formattedPace">
        <span>
          {{ $t('activityBellowMPillsComponent.labelAvgPace') }}
        </span>
        <span>
          <b>{{ formattedPace }}</b>
        </span>
      </div>
      <div class="d-flex justify-content-between mt-3" v-if="activity.total_elapsed_time">
        <span>
          {{ $t('activityBellowMPillsComponent.labelElapsedTime') }}
        </span>
        <span>
          <b>{{ formatSecondsToMinutes(activity.total_elapsed_time) }}</b>
        </span>
      </div>
      <div class="d-flex justify-content-between mt-3" v-if="activity.total_timer_time">
        <span>
          {{ $t('activityBellowMPillsComponent.labelMovingTime') }}
        </span>
        <span>
          <b>{{ formatSecondsToMinutes(activity.total_timer_time) }}</b>
        </span>
      </div>
      <hr />
    </div>
    <!-- Velocity values -->
    <div v-if="velPresent">
      <span class="fw-normal">
        {{ $t('activityBellowMPillsComponent.subTitleSpeed') }}
      </span>
      <ActivityStreamsLineChartComponent
        :activity="activity"
        :graphSelection="'vel'"
        :activityStreams="activityActivityStreams"
      />
      <div class="d-flex justify-content-between mt-3" v-if="activity.average_speed">
        <span>
          {{ $t('activityBellowMPillsComponent.labelAvgSpeed') }}
        </span>
        <span>
          <span v-if="activity.average_speed && units === 'metric'"
            ><b
              >{{ formatAverageSpeedMetric(activity.average_speed)
              }}{{ ' ' + $t('generalItems.unitsKmH') }}</b
            ></span
          >
          <span v-else-if="activity.average_speed && units === 'imperial'"
            ><b
              >{{ formatAverageSpeedImperial(activity.average_speed)
              }}{{ ' ' + $t('generalItems.unitsMph') }}</b
            ></span
          >
        </span>
      </div>
      <div class="d-flex justify-content-between mt-3" v-if="activity.max_speed">
        <span>
          {{ $t('activityBellowMPillsComponent.labelMaxSpeed') }}
        </span>
        <span>
          <span v-if="activity.max_speed && units === 'metric'"
            ><b
              >{{ formatAverageSpeedMetric(activity.max_speed)
              }}{{ ' ' + $t('generalItems.unitsKmH') }}</b
            ></span
          >
          <span v-else-if="activity.max_speed && units === 'imperial'"
            ><b
              >{{ formatAverageSpeedImperial(activity.max_speed)
              }}{{ ' ' + $t('generalItems.unitsMph') }}</b
            ></span
          >
        </span>
      </div>
      <div class="d-flex justify-content-between mt-3" v-if="activity.total_elapsed_time">
        <span>
          {{ $t('activityBellowMPillsComponent.labelMovingTime') }}
        </span>
        <span>
          <b>{{ formatSecondsToMinutes(activity.total_elapsed_time) }}</b>
        </span>
      </div>
      <div class="d-flex justify-content-between mt-3" v-if="activity.total_timer_time">
        <span>
          {{ $t('activityBellowMPillsComponent.labelElapsedTime') }}
        </span>
        <span>
          <b>{{ formatSecondsToMinutes(activity.total_timer_time) }}</b>
        </span>
      </div>
      <hr />
    </div>
    <!-- Heart rate values -->
    <div v-if="hrPresent">
      <span class="fw-normal">
        {{ $t('activityBellowMPillsComponent.subTitleHeartRate') }}
      </span>
      <ActivityStreamsLineChartComponent
        :activity="activity"
        :graphSelection="'hr'"
        :activityStreams="activityActivityStreams"
      />
      <div class="d-flex justify-content-between mt-3" v-if="activity.average_hr">
        <span>
          {{ $t('activityBellowMPillsComponent.labelAvgHeartRate') }}
        </span>
        <span>
          <b>{{ activity.average_hr }}{{ ' ' + $t('generalItems.unitsBpm') }}</b>
        </span>
      </div>
      <div class="d-flex justify-content-between mt-3" v-if="activity.max_hr">
        <span>
          {{ $t('activityBellowMPillsComponent.labelMaxHeartRate') }}
        </span>
        <span>
          <b>{{ activity.max_hr }}{{ ' ' + $t('generalItems.unitsBpm') }}</b>
        </span>
      </div>
      <BarChartComponent
        v-if="Object.values(hrZones).length > 0 && hrPresent"
        :labels="hrChartData.labels"
        :values="hrChartData.values"
        :barColors="hrChartData.barColors"
        :timeSeconds="hrChartData.timeSeconds"
        :datalabelsFormatter="
          (value, context) => formatHrZoneLabel(value, hrChartData.timeSeconds[context.dataIndex])
        "
        :title="$t('activityMandAbovePillsComponent.labelHRZones')"
      />
      <hr />
    </div>
    <!-- Power values -->
    <div v-if="powerPresent">
      <span class="fw-normal">
        {{ $t('activityBellowMPillsComponent.subTitlePower') }}
      </span>
      <ActivityStreamsLineChartComponent
        :activity="activity"
        :graphSelection="'power'"
        :activityStreams="activityActivityStreams"
      />
      <div class="d-flex justify-content-between mt-3" v-if="activity.average_power">
        <span>
          {{ $t('activityBellowMPillsComponent.labelAvgPower') }}
        </span>
        <span>
          <b>{{ activity.average_power }}{{ ' ' + $t('generalItems.unitsWattsShort') }}</b>
        </span>
      </div>
      <div class="d-flex justify-content-between mt-3" v-if="activity.max_power">
        <span>
          {{ $t('activityBellowMPillsComponent.labelMaxPower') }}
        </span>
        <span>
          <b>{{ activity.max_power }}{{ ' ' + $t('generalItems.unitsWattsShort') }}</b>
        </span>
      </div>
      <div class="d-flex justify-content-between mt-3" v-if="activity.normalized_power">
        <span>
          {{ $t('activityBellowMPillsComponent.labelNormalizedPower') }}
        </span>
        <span>
          <b>{{ activity.normalized_power }}{{ ' ' + $t('generalItems.unitsWattsShort') }}</b>
        </span>
      </div>
      <hr />
    </div>
    <!-- Cadence values -->
    <div v-if="cadPresent">
      <span class="fw-normal" v-if="!activityTypeIsSwimming(activity)">
        {{ $t('activityBellowMPillsComponent.subTitleCadence') }}
      </span>
      <span class="fw-normal" v-else>
        {{ $t('activityBellowMPillsComponent.subTitleStrokeRate') }}
      </span>
      <ActivityStreamsLineChartComponent
        :activity="activity"
        :graphSelection="'cad'"
        :activityStreams="activityActivityStreams"
      />
      <div class="d-flex justify-content-between mt-3" v-if="activity.average_cad">
        <span v-if="!activityTypeIsSwimming(activity)">
          {{ $t('activityBellowMPillsComponent.labelAvgCadence') }}
        </span>
        <span v-else>
          {{ $t('activityBellowMPillsComponent.labelAvgStrokeRate') }}
        </span>
        <span>
          <b>{{ activity.average_cad }}{{ ' ' + $t('generalItems.unitsSpm') }}</b>
        </span>
      </div>
      <div class="d-flex justify-content-between mt-3" v-if="activity.max_cad">
        <span v-if="!activityTypeIsSwimming(activity)">
          {{ $t('activityBellowMPillsComponent.labelMaxCadence') }}
        </span>
        <span v-else>
          {{ $t('activityBellowMPillsComponent.labelMaxStrokeRate') }}
        </span>
        <span>
          <b>{{ activity.max_cad }}{{ ' ' + $t('generalItems.unitsSpm') }}</b>
        </span>
      </div>
      <hr />
    </div>
    <!-- Elevation values -->
    <div v-if="elePresent && !activityTypeIsSwimming(activity)">
      <span class="fw-normal">
        {{ $t('activityBellowMPillsComponent.subTitleElevation') }}
      </span>
      <ActivityStreamsLineChartComponent
        :activity="activity"
        :graphSelection="'ele'"
        :activityStreams="activityActivityStreams"
      />
      <div class="d-flex justify-content-between mt-3" v-if="activity.elevation_gain">
        <span>
          {{ $t('activityBellowMPillsComponent.labelElevationGain') }}
        </span>
        <span v-if="units === 'metric'">
          <b>{{ activity.elevation_gain }}{{ ' ' + $t('generalItems.unitsM') }}</b>
        </span>
        <span v-else>
          <b
            >{{ metersToFeet(activity.elevation_gain)
            }}{{ ' ' + $t('generalItems.unitsFeetShort') }}</b
          >
        </span>
      </div>
      <div class="d-flex justify-content-between mt-3" v-if="activity.elevation_loss">
        <span>
          {{ $t('activityBellowMPillsComponent.labelElevationLoss') }}
        </span>
        <span v-if="units === 'metric'">
          <b>{{ activity.elevation_loss }}{{ ' ' + $t('generalItems.unitsM') }}</b>
        </span>
        <span v-else>
          <b
            >{{ metersToFeet(activity.elevation_loss)
            }}{{ ' ' + $t('generalItems.unitsFeetShort') }}</b
          >
        </span>
      </div>
      <hr />
    </div>

    <!-- sets -->
    <ActivityWorkoutStepsComponent
      :activity="activity"
      :activityActivityWorkoutSteps="activityActivityWorkoutSteps"
      :units="units"
      :activityActivityExerciseTitles="activityActivityExerciseTitles"
      :activityActivitySets="activityActivitySets"
      v-if="activityActivityWorkoutSteps && activityActivityWorkoutSteps.length > 0"
    />
  </div>
</template>

<script setup>
import { ref, onMounted, computed } from 'vue'
import { useI18n } from 'vue-i18n'
// Importing the components
import ActivityLapsComponent from '@/components/Activities/ActivityLapsComponent.vue'
import ActivityStreamsLineChartComponent from '@/components/Activities/ActivityStreamsLineChartComponent.vue'
import ActivityWorkoutStepsComponent from '@/components/Activities/ActivityWorkoutStepsComponent.vue'
import BarChartComponent from '@/components/GeneralComponents/BarChartComponent.vue'
// Import Notivue push
import { push } from 'notivue'
// Import the utils
import { getHrBarChartData, formatHrZoneLabel } from '@/utils/chartUtils'
import {
  formatPaceMetric,
  formatPaceImperial,
  formatPaceSwimMetric,
  formatPaceSwimImperial,
  formatAverageSpeedMetric,
  formatAverageSpeedImperial,
  activityTypeIsCycling,
  activityTypeNotCycling,
  activityTypeIsSwimming,
  activityTypeIsRowing,
  activityTypeIsSailing,
  activityTypeNotSailing,
  activityTypeIsWindsurf,
  activityTypeNotWindsurf
} from '@/utils/activityUtils'
import { formatSecondsToMinutes } from '@/utils/dateTimeUtils'
import { metersToFeet } from '@/utils/unitsUtils'

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
  activityActivityWorkoutSteps: {
    type: [Object, null],
    required: true
  },
  activityActivityStreams: {
    type: [Object, null],
    required: true
  },
  units: {
    type: String,
    default: 'metric'
  },
  activityActivityExerciseTitles: {
    type: [Object, null],
    required: true
  },
  activityActivitySets: {
    type: [Object, null],
    required: true
  }
})

// Setup composables and reactive data
const { t } = useI18n()
const hrPresent = ref(false)
const powerPresent = ref(false)
const elePresent = ref(false)
const cadPresent = ref(false)
const velPresent = ref(false)
const pacePresent = ref(false)
const formattedPace = ref(null)
const hrZones = ref({})

// Computed properties
const hrChartData = computed(() => getHrBarChartData(hrZones.value, t))

onMounted(async () => {
  try {
    if (props.activityActivityStreams && props.activityActivityStreams.length > 0) {
      // Check if the activity has the streams
      for (let i = 0; i < props.activityActivityStreams.length; i++) {
        if (props.activityActivityStreams[i].stream_type === 1) {
          hrPresent.value = true
          // If HR zones are present, add them to the hrZones object
          const hrStream = props.activityActivityStreams.find(
            (stream) => stream.hr_zone_percentages
          )
          hrZones.value =
            hrStream && hrStream.hr_zone_percentages ? hrStream.hr_zone_percentages : {}
        }
        if (props.activityActivityStreams[i].stream_type === 2) {
          powerPresent.value = true
        }
        if (props.activityActivityStreams[i].stream_type === 3) {
          cadPresent.value = true
        }
        if (props.activityActivityStreams[i].stream_type === 4) {
          elePresent.value = true
        }
        if (props.activityActivityStreams[i].stream_type === 5) {
          if (
            activityTypeIsCycling(props.activity) ||
            activityTypeIsSailing(props.activity) ||
            activityTypeIsWindsurf(props.activity)
          ) {
            velPresent.value = true
          }
        }
        if (props.activityActivityStreams[i].stream_type === 6) {
          if (
            activityTypeNotCycling(props.activity) &&
            activityTypeNotSailing(props.activity) &&
            activityTypeNotWindsurf(props.activity)
          ) {
            pacePresent.value = true
          }
        }
      }
    }
  } catch (error) {
    // If there is an error, set the error message and show the error alert.
    push.error(
      `${t('activityMandAbovePillsComponent.errorMessageProcessingActivityStreams')} - ${error}`
    )
  }

  try {
    if (activityTypeIsSwimming(props.activity) || activityTypeIsRowing(props.activity)) {
      if (props.units === 'metric') {
        formattedPace.value = computed(() => formatPaceSwimMetric(props.activity.pace))
      } else {
        formattedPace.value = computed(() => formatPaceSwimImperial(props.activity.pace))
      }
    } else {
      if (props.units === 'metric') {
        formattedPace.value = computed(() => formatPaceMetric(props.activity.pace))
      } else {
        formattedPace.value = computed(() => formatPaceImperial(props.activity.pace))
      }
    }
  } catch (error) {
    push.error(`${t('activitySummaryComponent.errorFetchingUserById')} - ${error}`)
  }
})
</script>
