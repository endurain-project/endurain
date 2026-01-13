<template>
  <h5>{{ t('userGoalsStatsComponent.title') }}</h5>
  <ul class="list-group list-group-flush" v-for="goal in goals" :key="goal.id" v-if="goals">
    <li class="list-group-item d-flex justify-content-between px-0 bg-body-tertiary">
      <div class="flex-grow-1">
        <div>
          <span v-if="goal.activity_type == 1">{{
            $t('userGoalsStatsComponent.activityTypeRun')
          }}</span>
          <span v-if="goal.activity_type == 2">{{
            $t('userGoalsStatsComponent.activityTypeBike')
          }}</span>
          <span v-if="goal.activity_type == 3">{{
            $t('userGoalsStatsComponent.activityTypeSwim')
          }}</span>
          <span v-if="goal.activity_type == 4">{{
            $t('userGoalsStatsComponent.activityTypeWalk')
          }}</span>
          <span v-if="goal.activity_type == 5">{{
            $t('userGoalsStatsComponent.activityTypeStrength')
          }}</span>
          <span v-if="goal.activity_type == 6">{{
            $t('userGoalsStatsComponent.activityTypeCardio')
          }}</span>
          <span> | </span>
          <span v-if="goal.interval == 'daily'">{{
            $t('userGoalsStatsComponent.intervalOption1')
          }}</span>
          <span v-if="goal.interval == 'weekly'">{{
            $t('userGoalsStatsComponent.intervalOption2')
          }}</span>
          <span v-if="goal.interval == 'monthly'">{{
            $t('userGoalsStatsComponent.intervalOption3')
          }}</span>
          <span v-if="goal.interval == 'yearly'">{{
            $t('userGoalsStatsComponent.intervalOption4')
          }}</span>
          <br />
          <span v-if="goal.goal_type === 1"
            >{{ goal.total_calories }} {{ $t('generalItems.unitsCalories')
            }}{{ $t('generalItems.ofWithSpaces') }}{{ goal.goal_calories }}
            {{ $t('generalItems.unitsCalories') }}</span
          >
          <span v-if="goal.goal_type === 2"
            >{{ goal.total_activities_number }}{{ $t('generalItems.ofWithSpaces')
            }}{{ goal.goal_activities_number }} {{ $t('userGoalsStatsComponent.activities') }}</span
          >
          <span v-if="goal.goal_type === 3"
            >{{ formatDistanceRaw(t, goal.total_distance, authStore.user.units, false)
            }}{{ $t('generalItems.ofWithSpaces')
            }}{{ formatDistanceRaw(t, goal.goal_distance, authStore.user.units) }}</span
          >
          <span v-if="goal.goal_type === 4 && authStore.user.units === 1"
            >{{ goal.total_elevation }}{{ $t('generalItems.ofWithSpaces')
            }}{{ goal.goal_elevation }} {{ $t('generalItems.unitsM') }}</span
          >
          <span v-if="goal.goal_type === 4 && authStore.user.units === 2"
            >{{ metersToFeet(goal.total_elevation) }}{{ $t('generalItems.ofWithSpaces')
            }}{{ metersToFeet(goal.goal_elevation) }} {{ $t('generalItems.unitsFt') }}</span
          >
          <span v-if="goal.goal_type === 5"
            >{{ formatDuration(goal.total_duration) }}{{ $t('generalItems.ofWithSpaces')
            }}{{ formatDuration(goal.goal_duration) }}</span
          >
        </div>
        <div
          class="progress"
          role="progressbar"
          aria-label="Goal tracking done vs target"
          :aria-valuenow="goal.percentage_completed"
          aria-valuemin="0"
          aria-valuemax="100"
        >
          <div
            class="progress-bar"
            :class="{ 'bg-success': goal.percentage_completed === 100 }"
            :style="{ width: goal.percentage_completed + '%' }"
          >
            {{ goal.percentage_completed }}%
          </div>
        </div>
      </div>
    </li>
  </ul>
  <NoItemsFoundComponents :show-shadow="false" v-else />
</template>

<script setup>
import { useI18n } from 'vue-i18n'
import { useAuthStore } from '@/stores/authStore'
import { formatDistanceRaw } from '@/utils/activityUtils'
import { formatDuration } from '@/utils/dateTimeUtils'
import { metersToFeet } from '@/utils/unitsUtils'

import NoItemsFoundComponents from '@/components/GeneralComponents/NoItemsFoundComponents.vue'

const props = defineProps({
  goals: {
    type: [Object, null],
    required: true
  }
})

const { t } = useI18n()
const authStore = useAuthStore()
</script>
