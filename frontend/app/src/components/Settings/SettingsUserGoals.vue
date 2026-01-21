<template>
  <div class="col">
    <div class="bg-body-tertiary rounded p-3 shadow-sm">
      <div class="row row-gap-3">
        <div class="col-lg-4 col-md-12">
          <!-- add goal button -->
          <a
            class="w-100 btn btn-primary"
            href="#"
            role="button"
            data-bs-toggle="modal"
            data-bs-target="#addGoalModal"
            >{{ $t('settingsUserGoalsZone.addNewGoal') }}</a
          >

          <!-- Modal goal user -->
          <GoalsAddEditGoalModalComponent
            :action="'add'"
            @createdGoal="addGoalList"
            @isLoadingNewGoal="setIsLoadingNewGoal"
          />
        </div>
      </div>
      <!-- Filter row -->
      <div class="row row-gap-3 my-3">
        <!-- Interval filter -->
        <div class="col-lg-3 col-md-12">
          <label for="intervalFilter" class="form-label">{{
            $t('settingsUserGoalsZone.filterByInterval')
          }}</label>
          <select
            id="intervalFilter"
            class="form-select form-select-sm"
            :disabled="isLoading"
            v-model="selectedInterval"
            @change="fetchGoals"
          >
            <option value="">{{ $t('settingsUserGoalsZone.filterAll') }}</option>
            <option value="daily">{{ $t('goalsAddEditGoalModalComponent.intervalDaily') }}</option>
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
        </div>
        <!-- Activity type filter -->
        <div class="col-lg-3 col-md-12">
          <label for="activityTypeFilter" class="form-label">{{
            $t('settingsUserGoalsZone.filterByActivityType')
          }}</label>
          <select
            id="activityTypeFilter"
            class="form-select form-select-sm"
            :disabled="isLoading"
            v-model="selectedActivityType"
            @change="fetchGoals"
          >
            <option value="">{{ $t('settingsUserGoalsZone.filterAll') }}</option>
            <option value="run">{{ $t('goalsAddEditGoalModalComponent.activityTypeRun') }}</option>
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
        </div>
        <!-- Goal type filter -->
        <div class="col-lg-3 col-md-12">
          <label for="goalTypeFilter" class="form-label">{{
            $t('settingsUserGoalsZone.filterByGoalType')
          }}</label>
          <select
            id="goalTypeFilter"
            class="form-select form-select-sm"
            :disabled="isLoading"
            v-model="selectedGoalType"
            @change="fetchGoals"
          >
            <option value="">{{ $t('settingsUserGoalsZone.filterAll') }}</option>
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
        </div>
        <!-- Clear filters button -->
        <div class="col-lg-3 col-md-12 d-flex align-items-end">
          <button
            type="button"
            class="btn btn-sm btn-secondary w-100"
            @click="clearFilters"
            :disabled="!hasActiveFilters || isLoading"
          >
            {{ $t('settingsUserGoalsZone.clearFilters') }}
          </button>
        </div>
      </div>

      <!-- loading state -->
      <LoadingComponent class="mt-3" v-if="isLoading" />
      <div v-else>
        <div v-if="(goalsArray && goalsArray.length) || hasActiveFilters">
          <span
            >{{ $t('settingsUserGoalsZone.labelNumberOfGoals1') }}{{ goalsArray.length
            }}{{ $t('settingsUserGoalsZone.labelNumberOfGoals2') }}</span
          >
          <!-- Displaying loading new goal if applicable -->
          <ul class="list-group list-group-flush" v-if="isLoadingNewGoal">
            <li class="list-group-item rounded">
              <LoadingComponent />
            </li>
          </ul>
          <!-- list zone -->
          <ul
            class="list-group list-group-flush"
            v-for="goal in goalsArray"
            :key="goal.id"
            :goal="goal"
            v-if="goalsArray && goalsArray.length"
          >
            <GoalsListComponent
              :goal="goal"
              @goalDeleted="updateGoalList"
              @editedGoal="editGoalList"
            />
          </ul>
          <NoItemsFoundComponents
            :show-shadow="false"
            v-if="goalsArray.length === 0 && hasActiveFilters"
          />
        </div>
        <NoItemsFoundComponents :show-shadow="false" v-else />
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import { ref, computed, onMounted } from 'vue'
import { push } from 'notivue'

import LoadingComponent from '@/components/GeneralComponents/LoadingComponent.vue'
import NoItemsFoundComponents from '@/components/GeneralComponents/NoItemsFoundComponents.vue'
import GoalsAddEditGoalModalComponent from '@/components/Settings/SettingsUserGoalsZone/GoalsAddEditGoalModalComponent.vue'
import GoalsListComponent from '@/components/Settings/SettingsUserGoalsZone/GoalsListComponent.vue'

import { userGoals as userGoalService } from '@/services/userGoalsService'

/**
 * Represents a user goal.
 *
 * @property id - Unique identifier for the goal.
 */
interface Goal {
  id: number
  [key: string]: unknown
}

const { t } = useI18n()

const goalsArray = ref<Goal[]>([])
const isLoading = ref(false)
const isLoadingNewGoal = ref(false)

// Filter values - storing selected filter value or empty string for "all"
const selectedActivityType = ref('')
const selectedGoalType = ref('')
const selectedInterval = ref('')

/**
 * Computed property to check if any filter is active.
 */
const hasActiveFilters = computed(() => {
  return (
    selectedActivityType.value !== '' ||
    selectedGoalType.value !== '' ||
    selectedInterval.value !== ''
  )
})

/**
 * Clears all active filters and refetches goals.
 */
async function clearFilters(): Promise<void> {
  selectedActivityType.value = ''
  selectedGoalType.value = ''
  selectedInterval.value = ''
  await fetchGoals()
}

/**
 * Fetches goals with current filter values.
 */
async function fetchGoals(): Promise<void> {
  isLoading.value = true
  try {
    const filters: { activity_type?: string; goal_type?: string; interval?: string } = {}
    if (selectedActivityType.value) filters.activity_type = selectedActivityType.value
    if (selectedGoalType.value) filters.goal_type = selectedGoalType.value
    if (selectedInterval.value) filters.interval = selectedInterval.value

    goalsArray.value = await (userGoalService as any).getUserGoals(filters)
  } catch (error) {
    push.error(`${t('settingsUserGoalsZone.errorFetchingGoals')} - ${error}`)
  } finally {
    isLoading.value = false
  }
}

/**
 * Sets the loading state for new goal creation.
 *
 * @param state - The loading state to set.
 */
function setIsLoadingNewGoal(state: boolean): void {
  isLoadingNewGoal.value = state
}

/**
 * Removes a deleted goal from the goals array.
 *
 * @param goalDeletedId - The id of the goal to remove.
 */
function updateGoalList(goalDeletedId: number): void {
  goalsArray.value = goalsArray.value.filter((goal) => goal.id !== goalDeletedId)
  push.success(t('settingsUserGoalsZone.successGoalDeleted'))
}

/**
 * Adds a newly created goal to the beginning of the goals array.
 *
 * @param createdGoal - The goal to add.
 */
function addGoalList(createdGoal: Goal): void {
  if (!Array.isArray(goalsArray.value)) {
    goalsArray.value = []
  }
  goalsArray.value.unshift(createdGoal)
}

/**
 * Updates an existing goal in the goals array.
 *
 * @param editedGoal - The goal with updated values.
 */
function editGoalList(editedGoal: Goal): void {
  const index = goalsArray.value.findIndex((goal) => goal.id === editedGoal.id)
  goalsArray.value[index] = editedGoal
}

onMounted(async () => {
  await fetchGoals()
})
</script>
