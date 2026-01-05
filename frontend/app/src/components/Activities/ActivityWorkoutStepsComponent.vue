<template>
  <div class="table-responsive d-none d-sm-block">
    <table
      v-if="largerLength"
      class="table table-striped table-borderless table-hover table-sm rounded text-center"
      style="--bs-table-bg: var(--bs-gray-850)"
    >
      <thead>
        <tr>
          <th>#</th>
          <th v-if="activityActivityWorkoutSteps && activityActivityWorkoutSteps.length > 0">
            {{ $t('activityWorkoutStepsComponent.labelWorkoutStepType') }}
          </th>
          <th v-if="activityActivityWorkoutSteps && activityActivityWorkoutSteps.length > 0">
            {{ $t('activityWorkoutStepsComponent.labelWorkoutStepTime') }}
          </th>
          <th
            v-if="
              (activity.activity_type === 10 ||
                activity.activity_type === 19 ||
                activity.activity_type === 20 ||
                activity.activity_type === 41 ||
                activity.activity_type === 46) &&
              activityActivityWorkoutSteps &&
              activityActivityWorkoutSteps.length > 0
            "
          >
            {{ $t('activityWorkoutStepsComponent.labelWorkoutStepReps') }}
          </th>
          <th
            v-if="
              (activity.activity_type === 10 ||
                activity.activity_type === 19 ||
                activity.activity_type === 20 ||
                activity.activity_type === 41 ||
                activity.activity_type === 46) &&
              activityActivityWorkoutSteps &&
              activityActivityWorkoutSteps.length > 0
            "
          >
            {{ $t('activityWorkoutStepsComponent.labelWorkoutStepExerciseName') }}
          </th>
          <th
            v-if="
              (activity.activity_type === 8 || activity.activity_type === 9) &&
              activityActivityWorkoutSteps &&
              activityActivityWorkoutSteps.length > 0
            "
          >
            {{ $t('activityWorkoutStepsComponent.labelWorkoutStepSwimStroke') }}
          </th>
          <!-- divide -->
          <th
            v-if="
              activityActivityWorkoutSteps &&
              activityActivityWorkoutSteps.length > 0 &&
              activityActivitySets &&
              activityActivitySets.length > 0
            "
          >
            |
          </th>
          <!-- sets -->
          <th v-if="activityActivitySets && activityActivitySets.length > 0">
            {{ $t('activityWorkoutStepsComponent.labelWorkoutSetType') }}
          </th>
          <th v-if="activityActivitySets && activityActivitySets.length > 0">
            {{ $t('activityWorkoutStepsComponent.labelWorkoutSetTime') }}
          </th>
          <th v-if="activityActivitySets && activityActivitySets.length > 0">
            {{ $t('activityWorkoutStepsComponent.labelWorkoutSetReps') }}
          </th>
          <th v-if="activityActivitySets && activityActivitySets.length > 0">
            {{ $t('activityWorkoutStepsComponent.labelWorkoutSetExerciseName') }}
          </th>
          <th v-if="activityActivitySets && activityActivitySets.length > 0">
            {{ $t('activityWorkoutStepsComponent.labelWorkoutSetExerciseWeight') }}
          </th>
        </tr>
      </thead>
      <tbody class="table-group-divider">
        <tr v-for="i in largerLength" :key="i">
          <td>{{ i }}</td>
          <td v-if="activityActivityWorkoutSteps && activityActivityWorkoutSteps.length > 0">
            <span v-if="processedWorkoutSteps[i - 1]">{{
              processedWorkoutSteps[i - 1].intensity ?? $t('generalItems.labelNoData')
            }}</span>
          </td>
          <td v-if="activityActivityWorkoutSteps && activityActivityWorkoutSteps.length > 0">
            <span
              v-if="
                processedWorkoutSteps[i - 1] &&
                processedWorkoutSteps[i - 1].duration_type === 'time'
              "
            >
              {{ formatSecondsToMinutes(processedWorkoutSteps[i - 1].duration_value) }}
            </span>
          </td>
          <td
            v-if="
              (activity.activity_type === 10 ||
                activity.activity_type === 19 ||
                activity.activity_type === 20 ||
                activity.activity_type === 41 ||
                activity.activity_type === 46) &&
              activityActivityWorkoutSteps &&
              activityActivityWorkoutSteps.length > 0
            "
          >
            <span
              v-if="
                processedWorkoutSteps[i - 1] &&
                processedWorkoutSteps[i - 1].duration_type === 'reps'
              "
            >
              {{ processedWorkoutSteps[i - 1].duration_value }}
            </span>
          </td>
          <td
            v-if="
              (activity.activity_type === 10 ||
                activity.activity_type === 19 ||
                activity.activity_type === 20 ||
                activity.activity_type === 41 ||
                activity.activity_type === 46) &&
              activityActivityWorkoutSteps &&
              activityActivityWorkoutSteps.length > 0
            "
          >
            <span
              v-if="
                processedWorkoutSteps[i - 1] &&
                activityActivityExerciseTitles &&
                activityActivityExerciseTitles.some(
                  (title) =>
                    title.exercise_name === processedWorkoutSteps[i - 1].exercise_name &&
                    title.exercise_category === processedWorkoutSteps[i - 1].exercise_category
                )
              "
            >
              {{
                activityActivityExerciseTitles.find(
                  (title) =>
                    title.exercise_name === processedWorkoutSteps[i - 1].exercise_name &&
                    title.exercise_category === processedWorkoutSteps[i - 1].exercise_category
                ).wkt_step_name
              }}
            </span>
            <span
              v-else-if="
                processedWorkoutSteps[i - 1] && processedWorkoutSteps[i - 1].intensity !== 'rest'
              "
            >
              {{ processedWorkoutSteps[i - 1].exercise_name ?? $t('generalItems.labelNoData') }}
            </span>
          </td>
          <td
            v-if="
              (activity.activity_type === 8 || activity.activity_type === 9) &&
              activityActivityWorkoutSteps &&
              activityActivityWorkoutSteps.length > 0
            "
          >
            <span
              v-if="
                processedWorkoutSteps[i - 1] &&
                processedWorkoutSteps[i - 1].target_type === 'swim_stroke'
              "
            >
              {{
                processedWorkoutSteps[i - 1].secondary_target_value ??
                $t('generalItems.labelNoData')
              }}
            </span>
          </td>
          <!-- divide -->
          <td
            v-if="
              activityActivityWorkoutSteps &&
              activityActivityWorkoutSteps.length > 0 &&
              activityActivitySets &&
              activityActivitySets.length > 0
            "
          >
            |
          </td>
          <!-- sets -->
          <td v-if="activityActivitySets && activityActivitySets.length > 0">
            <span v-if="activityActivitySets[i - 1]">{{
              activityActivitySets[i - 1].set_type ?? $t('generalItems.labelNoData')
            }}</span>
          </td>
          <td
            v-if="
              activityActivitySets && activityActivitySets.length > 0 && activityActivitySets[i - 1]
            "
          >
            <span v-if="activityActivitySets[i - 1]">{{
              formatSecondsToMinutes(activityActivitySets[i - 1].duration) ??
              $t('generalItems.labelNoData')
            }}</span>
          </td>
          <td v-if="activityActivitySets && activityActivitySets.length > 0">
            <span
              v-if="activityActivitySets[i - 1] && activityActivitySets[i - 1].set_type !== 'rest'"
            >
              {{ activityActivitySets[i - 1].repetitions ?? $t('generalItems.labelNoData') }}
            </span>
          </td>
          <td
            v-if="
              (activity.activity_type === 10 ||
                activity.activity_type === 19 ||
                activity.activity_type === 20 ||
                activity.activity_type === 41 ||
                activity.activity_type === 46) &&
              activityActivitySets &&
              activityActivitySets.length > 0
            "
          >
            <span
              v-if="
                activityActivitySets[i - 1] &&
                activityActivityExerciseTitles &&
                activityActivityExerciseTitles.some(
                  (title) =>
                    title.exercise_name === activityActivitySets[i - 1].category_subtype &&
                    title.exercise_category === activityActivitySets[i - 1].category
                ) &&
                activityActivitySets[i - 1].set_type !== 'rest'
              "
            >
              {{
                activityActivityExerciseTitles.find(
                  (title) =>
                    title.exercise_name === activityActivitySets[i - 1].category_subtype &&
                    title.exercise_category === activityActivitySets[i - 1].category
                ).wkt_step_name
              }}
            </span>
            <span
              v-else-if="
                activityActivitySets[i - 1] && activityActivitySets[i - 1].set_type !== 'rest'
              "
            >
              {{ activityActivitySets[i - 1].category_subtype ?? $t('generalItems.labelNoData') }}
            </span>
          </td>
          <td
            v-if="
              (activity.activity_type === 10 ||
                activity.activity_type === 19 ||
                activity.activity_type === 20 ||
                activity.activity_type === 41 ||
                activity.activity_type === 46) &&
              activityActivitySets &&
              activityActivitySets.length > 0
            "
          >
            <span
              v-if="activityActivitySets[i - 1] && activityActivitySets[i - 1].set_type !== 'rest'"
            >
              {{ activityActivitySets[i - 1].weight ?? $t('generalItems.labelNoData') }}
            </span>
          </td>
        </tr>
      </tbody>
    </table>
  </div>

  <div
    class="table-responsive d-lg-none d-block"
    v-if="activityActivitySets && activityActivitySets.length > 0"
  >
    <table class="table table-sm table-borderless" style="--bs-table-bg: var(--bs-gray-850)">
      <thead>
        <tr>
          <th>#</th>
          <th>{{ $t('activityWorkoutStepsComponent.labelWorkoutSetTypeMobile') }}</th>
          <th>{{ $t('activityWorkoutStepsComponent.labelWorkoutSetTimeMobile') }}</th>
          <th>{{ $t('activityWorkoutStepsComponent.labelWorkoutSetRepsMobile') }}</th>
          <th>{{ $t('activityWorkoutStepsComponent.labelWorkoutSetExerciseNameMobile') }}</th>
          <th>{{ $t('activityWorkoutStepsComponent.labelWorkoutSetExerciseWeightMobile') }}</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="i in activityActivitySets.length" :key="i">
          <td>{{ i }}</td>
          <td v-if="activityActivitySets[i - 1]">
            {{ activityActivitySets[i - 1].set_type ?? $t('generalItems.labelNoData') }}
          </td>
          <td v-if="activityActivitySets[i - 1]">
            {{
              formatSecondsToMinutes(activityActivitySets[i - 1].duration) ??
              $t('generalItems.labelNoData')
            }}
          </td>
          <td v-if="activityActivitySets[i - 1] && activityActivitySets[i - 1].set_type !== 'rest'">
            {{ activityActivitySets[i - 1].repetitions ?? $t('generalItems.labelNoData') }}
          </td>
          <td
            v-if="
              activityActivitySets[i - 1] &&
              activityActivityExerciseTitles &&
              activityActivityExerciseTitles.some(
                (title) =>
                  title.exercise_name === activityActivitySets[i - 1].category_subtype &&
                  title.exercise_category === activityActivitySets[i - 1].category
              ) &&
              activityActivitySets[i - 1].set_type !== 'rest'
            "
          >
            {{
              activityActivityExerciseTitles.find(
                (title) =>
                  title.exercise_name === activityActivitySets[i - 1].category_subtype &&
                  title.exercise_category === activityActivitySets[i - 1].category
              ).wkt_step_name
            }}
          </td>
          <td
            v-else-if="
              activityActivitySets[i - 1] && activityActivitySets[i - 1].set_type !== 'rest'
            "
          >
            {{ activityActivitySets[i - 1].category_subtype ?? $t('generalItems.labelNoData') }}
          </td>
          <td v-if="activityActivitySets[i - 1] && activityActivitySets[i - 1].set_type !== 'rest'">
            {{ activityActivitySets[i - 1].weight ?? $t('generalItems.labelNoData') }}
          </td>
        </tr>
      </tbody>
    </table>
  </div>
</template>

<script>
import { ref, computed } from 'vue'
// Importing the components
import LoadingComponent from '@/components/GeneralComponents/LoadingComponent.vue'
import { formatSecondsToMinutes } from '@/utils/dateTimeUtils'
import { formatPaceMetric } from '@/utils/activityUtils'
import { metersToKm } from '@/utils/unitsUtils'

export default {
  components: {
    LoadingComponent
  },
  props: {
    activity: {
      type: Object,
      required: true
    },
    activityActivityWorkoutSteps: {
      type: [Object, null],
      required: true
    },
    units: {
      type: Number,
      default: 1
    },
    activityActivityExerciseTitles: {
      type: [Object, null],
      required: true
    },
    activityActivitySets: {
      type: [Object, null],
      required: true
    }
  },
  setup(props) {
    const processedWorkoutSteps = computed(() => {
      if (!props.activityActivityWorkoutSteps) return []
      return props.activityActivityWorkoutSteps.reduce((result, step, index, array) => {
        if (step.duration_type === 'repeat_until_steps_cmplt') {
          const repeatCount = step.target_value
          const stepsToRepeat = array.slice(index - 2, index) // Get the two previous steps
          for (let i = 1; i < repeatCount; i++) {
            result.push(...stepsToRepeat) // Add the repeated steps
          }
        } else {
          result.push(step) // Add the current step if not "repeat_until_steps_cmplt"
        }
        return result
      }, [])
    })

    const largerLength = computed(() => {
      if (!props.activityActivityWorkoutSteps) {
        return props.activityActivitySets ? props.activityActivitySets.length : 0
      }
      if (!props.activityActivitySets) {
        return props.activityActivityWorkoutSteps ? props.activityActivityWorkoutSteps.length : 0
      }
      return Math.max(props.activityActivityWorkoutSteps.length, props.activityActivitySets.length)
    })

    return {
      formatSecondsToMinutes,
      formatPaceMetric,
      metersToKm,
      processedWorkoutSteps,
      largerLength
    }
  }
}
</script>
