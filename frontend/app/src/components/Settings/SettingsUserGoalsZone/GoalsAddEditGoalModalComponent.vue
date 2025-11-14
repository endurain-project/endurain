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
                {{ $t('goalsAddEditGoalModalComponent.intervalOption1') }}
              </option>
              <option value="weekly">
                {{ $t('goalsAddEditGoalModalComponent.intervalOption2') }}
              </option>
              <option value="monthly">
                {{ $t('goalsAddEditGoalModalComponent.intervalOption3') }}
              </option>
              <option value="yearly">
                {{ $t('goalsAddEditGoalModalComponent.intervalOption4') }}
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
              <option :value="1">{{ $t('goalsAddEditGoalModalComponent.activityTypeRun') }}</option>
              <option :value="2">
                {{ $t('goalsAddEditGoalModalComponent.activityTypeBike') }}
              </option>
              <option :value="3">
                {{ $t('goalsAddEditGoalModalComponent.activityTypeSwim') }}
              </option>
              <option :value="4">
                {{ $t('goalsAddEditGoalModalComponent.activityTypeWalk') }}
              </option>
              <option :value="5">
                {{ $t('goalsAddEditGoalModalComponent.activityTypeStrength') }}
              </option>
              <option :value="6">
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
              <option :value="1">
                {{ $t('goalsAddEditGoalModalComponent.addEditGoalModalCaloriesLabel') }}
              </option>
              <option :value="2">
                {{ $t('goalsAddEditGoalModalComponent.addEditGoalModalActivitiesNumberLabel') }}
              </option>
              <option :value="3">
                {{ $t('goalsAddEditGoalModalComponent.addEditGoalModalDistanceLabel') }}
              </option>
              <option :value="4">
                {{ $t('goalsAddEditGoalModalComponent.addEditGoalModalElevationLabel') }}
              </option>
              <option :value="5">
                {{ $t('goalsAddEditGoalModalComponent.addEditGoalModalDurationLabel') }}
              </option>
            </select>
            <!-- calories fields -->
            <div v-if="newEditGoalType === 1">
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
            <div v-if="newEditGoalType === 2">
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
            <div v-if="newEditGoalType === 3">
              <div v-if="Number(authStore?.user?.units) === 1">
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
            <div v-if="newEditGoalType === 4">
              <div v-if="Number(authStore?.user?.units) === 1">
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
            <div v-if="newEditGoalType === 5">
              <label for="goalDurationAddEdit"
                ><b>{{
                  $t('goalsAddEditGoalModalComponent.addEditGoalModalDurationLabel')
                }}</b></label
              >
              <input
                class="form-control"
                type="number"
                step="0.1"
                name="goalDurationAddEdit"
                :placeholder="
                  $t('goalsAddEditGoalModalComponent.addEditGoalModalDurationPlaceholder')
                "
                v-model="newEditGoalDuration"
              />
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
const newEditGoalActivityType = ref(1)
const newEditGoalType = ref(1)
const newEditGoalCalories = ref(null)
const newEditGoalActivitiesNumber = ref(null)
const newEditGoalDistanceMetric = ref(null)
const newEditGoalDistanceImperial = ref(null)
const newEditGoalElevationMetric = ref(null)
const newEditGoalElevationImperial = ref(null)
const newEditGoalDuration = ref(null)

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
    newEditGoalDuration.value = props.goal.goal_duration
  }
}

function setGoalObject() {
  let distance = null
  let elevation = null
  if (Number(authStore?.user?.units) === 2) {
    if (newEditGoalDistanceImperial.value) {
      distance = milesToMeters(newEditGoalDistanceImperial.value)
    }
    if (newEditGoalElevationImperial.value) {
      elevation = feetToMeters(newEditGoalElevationImperial.value)
    }
  } else if (Number(authStore?.user?.units) === 1) {
    if (newEditGoalDistanceMetric.value) {
      distance = kmToMeters(newEditGoalDistanceMetric.value)
    }
    if (newEditGoalElevationMetric.value) {
      elevation = newEditGoalElevationMetric.value
    }
  }
  return {
    interval: newEditGoalInterval.value,
    activity_type: newEditGoalActivityType.value,
    goal_type: newEditGoalType.value,
    goal_calories: newEditGoalCalories.value,
    goal_activities_number: newEditGoalActivitiesNumber.value,
    goal_distance: distance,
    goal_elevation: elevation,
    goal_duration: newEditGoalDuration.value
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
  try {
    const editedGoal = await userGoalsService.editGoal(props.goal.id, goalData)
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
