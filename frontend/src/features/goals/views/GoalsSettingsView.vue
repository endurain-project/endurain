<script setup lang="ts">
import { computed, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { Filter, Plus, Target } from '@lucide/vue'

import type {
  Goal,
  GoalActivityType,
  GoalFilters,
  GoalInterval,
  GoalMetric,
} from '@/features/goals/types'

import GoalFormDialog from '@/features/goals/components/GoalFormDialog.vue'
import GoalListItem from '@/features/goals/components/GoalListItem.vue'
import { Button } from '@/components/ui/button'
import { ConfirmDialog } from '@/components/ui/confirm-dialog'
import { CountBadge } from '@/components/ui/count-badge'
import { EmptyState } from '@/components/ui/empty-state'
import { FormField } from '@/components/ui/form-field'
import { ListPanel } from '@/components/ui/list-panel'
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover'
import { Select } from '@/components/ui/select'
import { Skeleton } from '@/components/ui/skeleton'
import { useToasts } from '@/composables/useToasts'
import { useCurrentUser } from '@/features/auth/composables/useCurrentUser'
import {
  ACTIVITY_TYPE_LABEL_KEYS,
  GOAL_ACTIVITY_TYPES,
  GOAL_INTERVALS,
  GOAL_METRICS,
  GOAL_METRIC_LABEL_KEYS,
  INTERVAL_LABEL_KEYS,
} from '@/features/goals/utils/goalFormat'
import { useDeleteGoalMutation, useGoalsQuery } from '@/features/goals/composables/useGoals'

const { t } = useI18n()
const toasts = useToasts()

const { data: currentUser } = useCurrentUser()
const units = computed(() => currentUser.value?.units ?? 'metric')

// Server-side filters (mirrors v1: changing a filter refetches with query params).
const selectedInterval = ref<GoalInterval | ''>('')
const selectedActivityType = ref<GoalActivityType | ''>('')
const selectedGoalType = ref<GoalMetric | ''>('')
const isFilterOpen = ref(false)

const filters = computed<GoalFilters>(() => ({
  interval: selectedInterval.value || null,
  activityType: selectedActivityType.value || null,
  goalType: selectedGoalType.value || null,
}))

const hasActiveFilters = computed(() =>
  Boolean(selectedInterval.value || selectedActivityType.value || selectedGoalType.value),
)
const activeFilterCount = computed(
  () =>
    [selectedInterval.value, selectedActivityType.value, selectedGoalType.value].filter(Boolean)
      .length,
)

/** Resets every goal filter to "all". */
function clearFilters(): void {
  selectedInterval.value = ''
  selectedActivityType.value = ''
  selectedGoalType.value = ''
}

const goalsQuery = useGoalsQuery(filters)
const deleteMutation = useDeleteGoalMutation()

const goals = computed(() => goalsQuery.data.value ?? [])
const isEmpty = computed(
  () => !goalsQuery.isPending.value && !goalsQuery.isError.value && goals.value.length === 0,
)

// Add/edit dialog state. A `null` target means "add".
const isFormOpen = ref(false)
const goalToEdit = ref<Goal | null>(null)

/** Opens the dialog in add mode. */
function openAdd(): void {
  goalToEdit.value = null
  isFormOpen.value = true
}

/** Opens the dialog in edit mode for the given goal. */
function openEdit(goal: Goal): void {
  goalToEdit.value = goal
  isFormOpen.value = true
}

// Delete confirmation state.
const isDeleteOpen = ref(false)
const goalToDelete = ref<Goal | null>(null)

/** Opens the delete confirmation for the given goal. */
function openDelete(goal: Goal): void {
  goalToDelete.value = goal
  isDeleteOpen.value = true
}

/** Deletes the pending goal and reports the outcome. */
function confirmDelete(): void {
  const goal = goalToDelete.value
  if (!goal) {
    return
  }
  deleteMutation.mutate(
    { id: goal.id, version: goal.version },
    {
      onSuccess: () => {
        isDeleteOpen.value = false
        toasts.success(t('settings.goals.delete.success'))
      },
      onError: () => toasts.error(t('settings.goals.delete.error')),
    },
  )
}
</script>

<template>
  <div class="flex flex-col gap-3">
    <div class="flex flex-wrap items-center justify-between gap-3">
      <div class="flex flex-col gap-1">
        <h1 class="text-page-title">{{ t('settings.goals.title') }}</h1>
        <p class="text-body">{{ t('settings.goals.subtitle') }}</p>
      </div>
      <Button class="w-full sm:w-auto" @click="openAdd">
        <Plus class="size-4" aria-hidden="true" />
        {{ t('settings.goals.buttonAdd') }}
      </Button>
    </div>

    <ListPanel
      :is-loading="goalsQuery.isPending.value"
      :is-error="goalsQuery.isError.value"
      :is-empty="isEmpty"
      :show-header="!goalsQuery.isError.value"
      :error-title="t('settings.goals.error.title')"
      :error-description="t('settings.goals.error.description')"
      :retry-label="t('settings.goals.error.retry')"
      @retry="goalsQuery.refetch()"
    >
      <template #header>
        <div class="flex items-center justify-between gap-3 px-4 py-3">
          <Skeleton v-if="goalsQuery.isPending.value" class="h-4 w-44" />
          <p v-else class="text-hint">{{ t('settings.goals.count', { count: goals.length }) }}</p>

          <Popover v-model:open="isFilterOpen">
            <PopoverTrigger as-child>
              <Button variant="outline" size="sm">
                <Filter class="size-4" aria-hidden="true" />
                {{ t('settings.goals.filters') }}
                <CountBadge :count="activeFilterCount" />
              </Button>
            </PopoverTrigger>
            <PopoverContent align="end" class="w-72">
              <div class="flex flex-col gap-3">
                <FormField :label="t('settings.goals.filter.interval')">
                  <template #default="{ fieldId }">
                    <Select :id="fieldId" v-model="selectedInterval">
                      <option value="">{{ t('settings.goals.filter.all') }}</option>
                      <option v-for="value in GOAL_INTERVALS" :key="value" :value="value">
                        {{ t(INTERVAL_LABEL_KEYS[value]) }}
                      </option>
                    </Select>
                  </template>
                </FormField>

                <FormField :label="t('settings.goals.filter.activityType')">
                  <template #default="{ fieldId }">
                    <Select :id="fieldId" v-model="selectedActivityType">
                      <option value="">{{ t('settings.goals.filter.all') }}</option>
                      <option v-for="value in GOAL_ACTIVITY_TYPES" :key="value" :value="value">
                        {{ t(ACTIVITY_TYPE_LABEL_KEYS[value]) }}
                      </option>
                    </Select>
                  </template>
                </FormField>

                <FormField :label="t('settings.goals.filter.goalType')">
                  <template #default="{ fieldId }">
                    <Select :id="fieldId" v-model="selectedGoalType">
                      <option value="">{{ t('settings.goals.filter.all') }}</option>
                      <option v-for="value in GOAL_METRICS" :key="value" :value="value">
                        {{ t(GOAL_METRIC_LABEL_KEYS[value]) }}
                      </option>
                    </Select>
                  </template>
                </FormField>

                <Button
                  variant="ghost"
                  size="sm"
                  class="self-end"
                  :disabled="!hasActiveFilters"
                  @click="clearFilters"
                >
                  {{ t('settings.goals.filter.clear') }}
                </Button>
              </div>
            </PopoverContent>
          </Popover>
        </div>
      </template>

      <template #empty>
        <EmptyState
          v-if="hasActiveFilters"
          :title="t('settings.goals.noMatch.title')"
          :description="t('settings.goals.noMatch.description')"
        >
          <template #icon>
            <Filter class="size-8" aria-hidden="true" />
          </template>
          <template #action>
            <Button variant="outline" @click="clearFilters">
              {{ t('settings.goals.filter.clear') }}
            </Button>
          </template>
        </EmptyState>
        <EmptyState
          v-else
          :title="t('settings.goals.empty.title')"
          :description="t('settings.goals.empty.description')"
        >
          <template #icon>
            <Target class="size-8" aria-hidden="true" />
          </template>
          <template #action>
            <Button @click="openAdd">
              <Plus class="size-4" aria-hidden="true" />
              {{ t('settings.goals.buttonAdd') }}
            </Button>
          </template>
        </EmptyState>
      </template>

      <ul class="divide-y divide-border">
        <li v-for="goal in goals" :key="goal.id">
          <GoalListItem :goal="goal" :units="units" @edit="openEdit" @delete="openDelete" />
        </li>
      </ul>
    </ListPanel>

    <GoalFormDialog
      v-model:open="isFormOpen"
      :goal="goalToEdit"
      :units="units"
      @success="(message) => toasts.success(message)"
      @error="(message) => toasts.error(message)"
    />

    <ConfirmDialog
      v-model:open="isDeleteOpen"
      :title="t('settings.goals.delete.title')"
      :description="t('settings.goals.delete.body')"
      :confirm-label="t('settings.goals.delete.confirm')"
      :cancel-label="t('settings.goals.delete.cancel')"
      :close-label="t('settings.goals.delete.close')"
      :pending="deleteMutation.isPending.value"
      @confirm="confirmDelete"
    />
  </div>
</template>
