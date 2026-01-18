<template>
  <!-- Modal add/edit goal -->
  <div
    class="modal fade"
    :id="action == 'add' ? 'addGoalModal' : action == 'edit' ? editGoalModalId : ''"
    tabindex="-1"
    :aria-labelledby="action == 'add' ? 'addGoalModal' : action == 'edit' ? editGoalModalId : ''"
    aria-hidden="true"
  >
    <div class="modal-dialog">
      <div class="modal-content">
        <div class="modal-header">
          <h1 class="modal-title fs-5" id="addGoalModal" v-if="action == 'add'">
            {{ $t('goalsAddEditGoalModalComponent.addEditGoalModalAddTitle') }}
          </h1>
          <h1 class="modal-title fs-5" :id="editGoalModalId" v-else-if="action == 'edit'">
            {{ $t('goalsAddEditGoalModalComponent.addEditGoalModalEditTitle') }}
          </h1>
          <button
            type="button"
            class="btn-close"
            data-bs-dismiss="modal"
            aria-label="Close"
          ></button>
        </div>
        <form @submit.prevent="handleSubmit">
          <div class="modal-body">
            <!-- interval fields -->
            <label for="goalIntervalAddEdit"
              ><b
                >* {{ $t('goalsAddEditGoalModalComponent.addEditGoalModalGoalIntervalLabel') }}</b
              ></label
            >
            <select
              class="form-select"
              name="goalIntervalAddEdit"
              v-model="newEditGoalInterval"
              required
            >
              <option value="daily">
                {{ $t('goalsAddEditGoalModalComponent.intervalDaily') }}
              </option>
              <option value="weekly">
                {{ $t('goalsAddEditGoalModalComponent.intervalWeekly') }}
              </option>
              <option value="monthly">
                {{ $t('goalsAddEditGoalModalComponent.intervalMonthly') }}
              </option>
              <option value="yearly">
                {{ $t('goalsAddEditGoalModalComponent.intervalYearly') }}
              </option>
            </select>
            <!-- activity type fields -->
            <label for="goalActivityTypeAddEdit"
              ><b
                >*
                {{ $t('goalsAddEditGoalModalComponent.addEditGoalModalGoalActivityTypeLabel') }}</b
              ></label
            >
            <select
              class="form-select"
              name="goalActivityTypeAddEdit"
              v-model="newEditGoalActivityType"
              required
            >
              <option value="run">
                {{ $t('goalsAddEditGoalModalComponent.activityTypeRun') }}
              </option>
              <option value="bike">
                {{ $t('goalsAddEditGoalModalComponent.activityTypeBike') }}
              </option>
              <option value="swim">
                {{ $t('goalsAddEditGoalModalComponent.activityTypeSwim') }}
              </option>
              <option value="walk">
                {{ $t('goalsAddEditGoalModalComponent.activityTypeWalk') }}
              </option>
              <option value="strength">
                {{ $t('goalsAddEditGoalModalComponent.activityTypeStrength') }}
              </option>
              <option value="cardio">
                {{ $t('goalsAddEditGoalModalComponent.activityTypeCardio') }}
              </option>
            </select>
            <!-- goal type fields -->
            <label for="goalTypeAddEdit"
              ><b
                >* {{ $t('goalsAddEditGoalModalComponent.addEditGoalModalGoalTypeLabel') }}</b
              ></label
            >
            <select class="form-select" name="goalTypeAddEdit" v-model="newEditGoalType" required>
              <option value="calories">
                {{ $t('goalsAddEditGoalModalComponent.addEditGoalModalCaloriesLabel') }}
              </option>
              <option value="activities">
                {{ $t('goalsAddEditGoalModalComponent.addEditGoalModalActivitiesNumberLabel') }}
              </option>
              <option value="distance">
                {{ $t('goalsAddEditGoalModalComponent.addEditGoalModalDistanceLabel') }}
              </option>
              <option value="elevation">
                {{ $t('goalsAddEditGoalModalComponent.addEditGoalModalElevationLabel') }}
              </option>
              <option value="duration">
                {{ $t('goalsAddEditGoalModalComponent.addEditGoalModalDurationLabel') }}
              </option>
            </select>
            <!-- calories fields -->
            <div v-if="newEditGoalType === 'calories'">
              <label for="goalCaloriesAddEdit"
                ><b>{{
                  $t('goalsAddEditGoalModalComponent.addEditGoalModalCaloriesLabel')
                }}</b></label
              >
              <input
                class="form-control"
                type="number"
                name="goalCaloriesAddEdit"
                :placeholder="
                  $t('goalsAddEditGoalModalComponent.addEditGoalModalCaloriesPlaceholder')
                "
                v-model="newEditGoalCalories"
              />
            </div>
            <!-- activities number fields -->
            <div v-if="newEditGoalType === 'activities'">
              <label for="goalActivitiesNumberAddEdit"
                ><b>{{
                  $t('goalsAddEditGoalModalComponent.addEditGoalModalActivitiesNumberLabel')
                }}</b></label
              >
              <input
                class="form-control"
                type="number"
                name="goalActivitiesNumberAddEdit"
                :placeholder="
                  $t('goalsAddEditGoalModalComponent.addEditGoalModalActivitiesNumberPlaceholder')
                "
                v-model="newEditGoalActivitiesNumber"
              />
            </div>
            <!-- distance fields -->
            <div v-if="newEditGoalType === 'distance'">
              <div v-if="authStore?.user?.units === 'metric'">
                <label for="goalDistanceMetricAddEdit"
                  ><b>{{
                    $t('goalsAddEditGoalModalComponent.addEditGoalModalDistanceLabel')
                  }}</b></label
                >
                <div class="input-group">
                  <input
                    class="form-control"
                    type="number"
                    name="goalDistanceMetricAddEdit"
                    :placeholder="
                      $t('goalsAddEditGoalModalComponent.addEditGoalModalDistancePlaceholder')
                    "
                    v-model="newEditGoalDistanceMetric"
                  />
                  <span class="input-group-text">{{ $t('generalItems.unitsKm') }}</span>
                </div>
              </div>
              <div v-else>
                <label for="goalDistanceImperialAddEdit"
                  ><b>{{
                    $t('goalsAddEditGoalModalComponent.addEditGoalModalDistanceLabel')
                  }}</b></label
                >
                <div class="input-group">
                  <input
                    class="form-control"
                    type="number"
                    name="goalDistanceImperialAddEdit"
                    :placeholder="
                      $t('goalsAddEditGoalModalComponent.addEditGoalModalDistancePlaceholder')
                    "
                    v-model="newEditGoalDistanceImperial"
                  />
                  <span class="input-group-text">{{ $t('generalItems.unitsMiles') }}</span>
                </div>
              </div>
            </div>
            <!-- elevation fields -->
            <div v-if="newEditGoalType === 'elevation'">
              <div v-if="authStore?.user?.units === 'metric'">
                <label for="goalElevationMetricAddEdit"
                  ><b>{{
                    $t('goalsAddEditGoalModalComponent.addEditGoalModalElevationLabel')
                  }}</b></label
                >
                <div class="input-group">
                  <input
                    class="form-control"
                    type="number"
                    name="goalElevationMetricAddEdit"
                    :placeholder="
                      $t('goalsAddEditGoalModalComponent.addEditGoalModalElevationPlaceholder')
                    "
                    v-model="newEditGoalElevationMetric"
                  />
                  <span class="input-group-text">{{ $t('generalItems.unitsM') }}</span>
                </div>
              </div>
              <div v-else>
                <label for="goalElevationImperialAddEdit"
                  ><b>{{
                    $t('goalsAddEditGoalModalComponent.addEditGoalModalElevationLabel')
                  }}</b></label
                >
                <div class="input-group">
                  <input
                    class="form-control"
                    type="number"
                    name="goalElevationImperialAddEdit"
                    :placeholder="
                      $t('goalsAddEditGoalModalComponent.addEditGoalModalElevationPlaceholder')
                    "
                    v-model="newEditGoalElevationImperial"
                  />
                  <span class="input-group-text">{{ $t('generalItems.unitsFeetShort') }}</span>
                </div>
              </div>
            </div>
            <!-- duration value fields -->
            <div v-if="newEditGoalType === 'duration'">
              <label for="goalDurationAddEdit"
                ><b>{{
                  $t('goalsAddEditGoalModalComponent.addEditGoalModalDurationLabel')
                }}</b></label
              >
              <div class="d-flex">
                <div class="input-group me-1">
                  <input
                    class="form-control"
                    type="number"
                    name="goalDurationHoursAddEdit"
                    :placeholder="$t('generalItems.labelHours')"
                    v-model="newEditGoalDurationHours"
                  />
                  <span class="input-group-text">{{ $t('generalItems.labelHoursShort') }}</span>
                </div>
                <div class="input-group ms-1">
                  <input
                    class="form-control"
                    type="number"
                    name="goalDurationMinutesAddEdit"
                    :placeholder="$t('generalItems.labelMinutes')"
                    v-model="newEditGoalDurationMinutes"
                  />
                  <span class="input-group-text">{{ $t('generalItems.labelMinutesShort') }}</span>
                </div>
              </div>
            </div>

            <p>* {{ $t('generalItems.requiredField') }}</p>
          </div>
          <div class="modal-footer">
            <button type="button" class="btn btn-secondary" data-bs-dismiss="modal">
              {{ $t('generalItems.buttonClose') }}
            </button>
            <button
              type="submit"
              class="btn btn-success"
              name="goalAdd"
              data-bs-dismiss="modal"
              v-if="action == 'add'"
            >
              {{ $t('goalsAddEditGoalModalComponent.addEditGoalModalAddTitle') }}
            </button>
            <button
              type="submit"
              class="btn btn-success"
              name="goalEdit"
              data-bs-dismiss="modal"
              v-else-if="action == 'edit'"
            >
              {{ $t('goalsAddEditGoalModalComponent.addEditGoalModalEditTitle') }}
            </button>
          </div>
        </form>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { push } from 'notivue'

import { useAuthStore } from '@/stores/authStore'
import {
  feetToMeters,
  milesToMeters,
  kmToMeters,
  metersToMiles,
  metersToFeet,
  metersToKm
} from '@/utils/unitsUtils'
import { returnHoursMinutesFromSeconds, returnSecondsFromHoursMinutes } from '@/utils/dateTimeUtils'

import { userGoals as userGoalsService } from '@/services/userGoalsService'

const props = defineProps({
  action: {
    type: String,
    required: true
  },
  goal: {
    type: Object,
    required: false
  }
})
const emit = defineEmits(['isLoadingNewGoal', 'createdGoal', 'editedGoal'])

const { t } = useI18n()
const authStore = useAuthStore()
const editGoalModalId = ref('')
const newEditGoalInterval = ref('daily')
const newEditGoalActivityType = ref('run')
const newEditGoalType = ref('calories')
const newEditGoalCalories = ref(null)
const newEditGoalActivitiesNumber = ref(null)
const newEditGoalDistanceMetric = ref(null)
const newEditGoalDistanceImperial = ref(null)
const newEditGoalElevationMetric = ref(null)
const newEditGoalElevationImperial = ref(null)
const newEditGoalDurationHours = ref(null)
const newEditGoalDurationMinutes = ref(null)

if (props.goal) {
  if (props.action === 'edit') {
    editGoalModalId.value = `editGoalModal${props.goal.id}`
    newEditGoalInterval.value = props.goal.interval
    newEditGoalActivityType.value = props.goal.activity_type
    newEditGoalType.value = props.goal.goal_type
    newEditGoalCalories.value = props.goal.goal_calories
    newEditGoalActivitiesNumber.value = props.goal.goal_activities_number
    if (props.goal.goal_distance) {
      newEditGoalDistanceMetric.value = Math.round(metersToKm(props.goal.goal_distance))
      newEditGoalDistanceImperial.value = Math.round(metersToMiles(props.goal.goal_distance))
    }
    if (props.goal.goal_elevation) {
      newEditGoalElevationMetric.value = props.goal.goal_elevation
      newEditGoalElevationImperial.value = metersToFeet(props.goal.goal_elevation)
    }
    const { hours, minutes } = returnHoursMinutesFromSeconds(props.goal.goal_duration)
    newEditGoalDurationHours.value = hours
    newEditGoalDurationMinutes.value = minutes
  }
}

function setGoalObject() {
  let distance = null
  let elevation = null
  let duration = null

  // Only set the field that matches the selected goal type
  if (newEditGoalType.value === 'distance') {
    // Distance goal
    if (authStore?.user?.units === 'imperial') {
      if (newEditGoalDistanceImperial.value) {
        distance = Math.round(milesToMeters(newEditGoalDistanceImperial.value))
      }
    } else if (authStore?.user?.units === 'metric') {
      if (newEditGoalDistanceMetric.value) {
        distance = Math.round(kmToMeters(newEditGoalDistanceMetric.value))
      }
    }
  } else if (newEditGoalType.value === 'elevation') {
    // Elevation goal
    if (authStore?.user?.units === 'imperial') {
      if (newEditGoalElevationImperial.value) {
        elevation = Math.round(feetToMeters(newEditGoalElevationImperial.value))
      }
    } else if (authStore?.user?.units === 'metric') {
      if (newEditGoalElevationMetric.value) {
        elevation = Math.round(newEditGoalElevationMetric.value)
      }
    }
  } else if (newEditGoalType.value === 'duration') {
    // Duration goal
    if (newEditGoalDurationHours.value || newEditGoalDurationMinutes.value) {
      duration = returnSecondsFromHoursMinutes(
        newEditGoalDurationHours.value ? parseInt(newEditGoalDurationHours.value) : 0,
        newEditGoalDurationMinutes.value ? parseInt(newEditGoalDurationMinutes.value) : 0
      )
    }
  }

  return {
    interval: newEditGoalInterval.value,
    activity_type: newEditGoalActivityType.value,
    goal_type: newEditGoalType.value,
    goal_calories:
      newEditGoalType.value === 'calories' && newEditGoalCalories.value
        ? parseInt(newEditGoalCalories.value)
        : null,
    goal_activities_number:
      newEditGoalType.value === 'activities' && newEditGoalActivitiesNumber.value
        ? parseInt(newEditGoalActivitiesNumber.value)
        : null,
    goal_distance: distance,
    goal_elevation: elevation,
    goal_duration: duration
  }
}

async function submitAddGoalForm() {
  emit('isLoadingNewGoal', true)
  const goalData = setGoalObject()
  try {
    const createdGoal = await userGoalsService.createGoal(goalData)
    emit('isLoadingNewGoal', false)
    emit('createdGoal', createdGoal)
    push.success(t('goalsAddEditGoalModalComponent.addEditGoalModalSuccessAddGoal'))
  } catch (error) {
    push.error(`${t('goalsAddEditGoalModalComponent.addEditGoalModalErrorAddGoal')} - ${error}`)
  } finally {
    emit('isLoadingNewGoal', false)
  }
}

async function submitEditGoalForm() {
  const goalData = setGoalObject()
  goalData.id = props.goal.id
  goalData.user_id = props.goal.user_id
  try {
    const editedGoal = await userGoalsService.editGoal(goalData)
    emit('editedGoal', editedGoal)
    push.success(t('goalsAddEditGoalModalComponent.addEditGoalModalSuccessEditGoal'))
  } catch (error) {
    push.error(`${t('goalsAddEditGoalModalComponent.addEditGoalModalErrorEditGoal')} - ${error}`)
  }
}

function handleSubmit() {
  if (props.action === 'add') {
    submitAddGoalForm()
  } else {
    submitEditGoalForm()
  }
}
</script>
