<template>
  <li class="list-group-item bg-body-tertiary rounded px-0">
    <div class="d-flex justify-content-between">
      <div class="d-flex align-items-center">
        <font-awesome-icon
          class="ms-2 me-1"
          icon="fa-solid fa-person-running"
          size="2x"
          v-if="goal.activity_type == 1"
        />
        <font-awesome-icon
          icon="fa-solid fa-person-biking"
          size="2x"
          v-else-if="goal.activity_type == 2"
        />
        <font-awesome-icon
          class="ms-1"
          icon="fa-solid fa-person-swimming"
          size="2x"
          v-else-if="goal.activity_type == 3"
        />
        <font-awesome-icon
          class="ms-2 me-2"
          icon="fa-solid fa-person-walking"
          size="2x"
          v-else-if="goal.activity_type == 4"
        />
        <font-awesome-icon icon="fa-solid fa-dumbbell" size="2x" v-else />
        <div class="ms-3">
          <div class="fw-bold">
            <span v-if="goal.activity_type == 1">{{
              $t('goalsAddEditGoalModalComponent.activityTypeRun')
            }}</span>
            <span v-if="goal.activity_type == 2">{{
              $t('goalsAddEditGoalModalComponent.activityTypeBike')
            }}</span>
            <span v-if="goal.activity_type == 3">{{
              $t('goalsAddEditGoalModalComponent.activityTypeSwim')
            }}</span>
            <span v-if="goal.activity_type == 4">{{
              $t('goalsAddEditGoalModalComponent.activityTypeWalk')
            }}</span>
            <span v-if="goal.activity_type == 5">{{
              $t('goalsAddEditGoalModalComponent.activityTypeStrength')
            }}</span>
            <span v-if="goal.activity_type == 6">{{
              $t('goalsAddEditGoalModalComponent.activityTypeCardio')
            }}</span>
          </div>
          <span v-if="goal.interval == 'daily'">{{
            $t('goalsAddEditGoalModalComponent.intervalOption1')
          }}</span>
          <span v-if="goal.interval == 'weekly'">{{
            $t('goalsAddEditGoalModalComponent.intervalOption2')
          }}</span>
          <span v-if="goal.interval == 'monthly'">{{
            $t('goalsAddEditGoalModalComponent.intervalOption3')
          }}</span>
          <span v-if="goal.interval == 'yearly'">{{
            $t('goalsAddEditGoalModalComponent.intervalOption4')
          }}</span>
          <span> | </span>
          <span v-if="goal.goal_type == 1"
            >{{ $t('goalsAddEditGoalModalComponent.addEditGoalModalCaloriesLabel') }} -
            {{ goal.goal_calories }} {{ $t('generalItems.unitsCalories') }}</span
          >
          <span v-if="goal.goal_type == 2"
            >{{ $t('goalsAddEditGoalModalComponent.addEditGoalModalActivitiesNumberLabel') }} -
            {{ goal.goal_activities_number }}</span
          >
          <span v-if="goal.goal_type == 3"
            >{{ $t('goalsAddEditGoalModalComponent.addEditGoalModalDistanceLabel') }} -
            <span v-if="authStore.user.units === 1"
              >{{ metersToKm(goal.goal_distance) }} {{ $t('generalItems.unitsKm') }}</span
            ><span v-else
              >{{ metersToMiles(goal.goal_distance) }} {{ $t('generalItems.unitsMiles') }}</span
            >
          </span>
          <span v-if="goal.goal_type == 4">
            {{ $t('goalsAddEditGoalModalComponent.addEditGoalModalElevationLabel') }} -
            <span v-if="authStore.user.units === 1"
              >{{ goal.goal_elevation }} {{ $t('generalItems.unitsM') }}</span
            ><span v-else
              >{{ metersToFeet(goal.goal_elevation) }} {{ $t('generalItems.unitsFeetShort') }}</span
            >
          </span>
          <span v-if="goal.goal_type == 5"
            >{{ $t('goalsAddEditGoalModalComponent.addEditGoalModalDurationLabel') }} -
            {{ formatDuration(goal.goal_duration) }}</span
          >
        </div>
      </div>
      <div>
        <!-- edit goal button -->
        <a
          class="btn btn-link btn-lg link-body-emphasis"
          href="#"
          role="button"
          data-bs-toggle="modal"
          :data-bs-target="`#editGoalModal${goal.id}`"
          ><font-awesome-icon :icon="['fas', 'fa-pen-to-square']"
        /></a>

        <!-- edit user modal -->
        <GoalsAddEditGoalModalComponent :action="'edit'" :goal="goal" @editedGoal="editGoalList" />

        <!-- delete goal button -->
        <a
          class="btn btn-link btn-lg link-body-emphasis"
          href="#"
          role="button"
          data-bs-toggle="modal"
          :data-bs-target="`#deleteGoalModal${goal.id}`"
          ><font-awesome-icon :icon="['fas', 'fa-trash-can']"
        /></a>

        <!-- delete goal modal -->
        <ModalComponent
          :modalId="`deleteGoalModal${goal.id}`"
          :title="t('goalsListComponent.modalDeleteGoalTitle')"
          :body="`${t('goalsListComponent.modalDeleteGoalBody')}<b>${goal.id}</b>?`"
          :actionButtonType="`danger`"
          :actionButtonText="t('goalsListComponent.modalDeleteGoalTitle')"
          @submitAction="submitDeleteGoal"
        />
      </div>
    </div>
  </li>
</template>

<script setup>
import { useAuthStore } from '@/stores/authStore'
import { useI18n } from 'vue-i18n'
import { push } from 'notivue'

import ModalComponent from '@/components/Modals/ModalComponent.vue'
import GoalsAddEditGoalModalComponent from '@/components/Settings/SettingsUserGoalsZone/GoalsAddEditGoalModalComponent.vue'

import { metersToKm, metersToMiles, metersToFeet } from '@/utils/unitsUtils'
import { formatDuration } from '@/utils/dateTimeUtils'

import { userGoals as userGoalService } from '@/services/userGoalsService'

const props = defineProps({
  goal: {
    type: Object,
    required: true
  }
})

const emit = defineEmits(['goalDeleted', 'editedGoal'])

const { t } = useI18n()
const authStore = useAuthStore()

function editGoalList(editedGoal) {
  emit('editedGoal', editedGoal)
}

async function submitDeleteGoal() {
  try {
    await userGoalService.deleteGoal(props.goal.id)
    emit('goalDeleted', props.goal.id)
  } catch (error) {
    push.error(`${t('goalsListComponent.goalDeleteErrorMessage')} - ${error}`)
  }
}
</script>
