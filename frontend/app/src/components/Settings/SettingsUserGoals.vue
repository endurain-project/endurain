<template>
  <div class="col">
    <div class="bg-body-tertiary rounded p-3 shadow-sm">
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

      <!-- loading state -->
      <LoadingComponent class="mt-3" v-if="isLoading" />
      <div v-else>
        <div class="mt-3" v-if="goalsArray && goalsArray.length">
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
        </div>
        <NoItemsFoundComponents :show-shadow="false" v-else />
      </div>
    </div>
  </div>
</template>

<script setup>
import { useI18n } from 'vue-i18n'
import { ref, onMounted } from 'vue'
import { push } from 'notivue'

import LoadingComponent from '@/components/GeneralComponents/LoadingComponent.vue'
import NoItemsFoundComponents from '@/components/GeneralComponents/NoItemsFoundComponents.vue'
import GoalsAddEditGoalModalComponent from '@/components/Settings/SettingsUserGoalsZone/GoalsAddEditGoalModalComponent.vue'
import GoalsListComponent from '@/components/Settings/SettingsUserGoalsZone/GoalsListComponent.vue'

import { userGoals as userGoalService } from '@/services/userGoalsService'

const { t } = useI18n()

const goalsArray = ref([])
const isLoading = ref(false)
const isLoadingNewGoal = ref(false)

function setIsLoadingNewGoal(state) {
  isLoadingNewGoal.value = state
}

function updateGoalList(goalDeletedId) {
  goalsArray.value = goalsArray.value.filter((goal) => goal.id !== goalDeletedId)
  push.success(t('settingsUserGoalsZone.successGoalDeleted'))
}

function addGoalList(createdGoal) {
  if (!Array.isArray(goalsArray.value)) {
    goalsArray.value = []
  }
  goalsArray.value.unshift(createdGoal)
}

function editGoalList(editedGoal) {
  const index = goalsArray.value.findIndex((goal) => goal.id === editedGoal.id)
  goalsArray.value[index] = editedGoal
}

onMounted(async () => {
  isLoading.value = true
  try {
    goalsArray.value = await userGoalService.getUserGoals()
  } catch (error) {
    push.error(`${t('settingsUserGoalsZone.errorFetchingGoals')} - ${error}`)
  } finally {
    isLoading.value = false
  }
})
</script>
