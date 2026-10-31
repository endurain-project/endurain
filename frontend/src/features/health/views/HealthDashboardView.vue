<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'

import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
import { ErrorState } from '@/components/ui/error-state'
import HealthDashboardCard from '@/features/health/components/HealthDashboardCard.vue'
import { useCurrentUser } from '@/features/auth/composables/useCurrentUser'
import { useHealthDashboardQuery } from '@/features/health/composables/useHealth'
import {
  bmiCategoryKey,
  fastingElapsedSeconds,
  formatBmi,
  formatHoursMinutes,
  formatRestingHeartRate,
  formatSkinTempDeviation,
  formatSteps,
  formatWater,
  formatWeight,
  hrvStatusKey,
} from '@/features/health/utils/healthFormat'

/**
 * Health dashboard zone. Renders a grid of metric cards combining today's
 * health stats with the user's targets (target value + an up/down arrow), in
 * the user's unit system. Mirrors v1's HealthDashboardZoneComponent.
 */
const { t } = useI18n()

const dashboardQuery = useHealthDashboardQuery()
const { data: user } = useCurrentUser()

const units = computed(() => user.value?.units ?? 'metric')
const dashboard = computed(() => dashboardQuery.data.value ?? null)
const targets = computed(() => dashboard.value?.targets ?? null)

const isLoading = computed(() => dashboardQuery.isPending.value)
const isError = computed(() => dashboardQuery.isError.value)

/** Refetches the dashboard (the error state's retry affordance). */
function refetch(): void {
  void dashboardQuery.refetch()
}

/**
 * The arrow direction comparing an actual value against its target.
 *
 * @param actual - The current metric value, or `null`.
 * @param target - The target value, or `null`.
 * @returns `'up'` at/above target, `'down'` below, or `null` when incomparable.
 */
function arrow(actual: number | null, target: number | null): 'up' | 'down' | null {
  if (actual === null || target === null) return null
  return actual >= target ? 'up' : 'down'
}

/** Resolves an HRV status to its translated label, or `null`. */
function hrvLabel(status: string | null): string | null {
  const key = status ? hrvStatusKey(status) : null
  switch (key) {
    case 'hrvBalanced':
      return t('health.dashboard.hrvBalanced')
    case 'hrvUnbalanced':
      return t('health.dashboard.hrvUnbalanced')
    case 'hrvLow':
      return t('health.dashboard.hrvLow')
    case 'hrvPoor':
      return t('health.dashboard.hrvPoor')
    default:
      return null
  }
}

/** Resolves a BMI value to its translated category label, or `null`. */
function bmiLabel(bmi: number | null): string | null {
  if (bmi === null) return null
  switch (bmiCategoryKey(bmi)) {
    case 'bmiUnderweight':
      return t('health.dashboard.bmiUnderweight')
    case 'bmiNormalWeight':
      return t('health.dashboard.bmiNormalWeight')
    case 'bmiOverweight':
      return t('health.dashboard.bmiOverweight')
    case 'bmiObesityClass1':
      return t('health.dashboard.bmiObesityClass1')
    case 'bmiObesityClass2':
      return t('health.dashboard.bmiObesityClass2')
    case 'bmiObesityClass3':
      return t('health.dashboard.bmiObesityClass3')
    default:
      return null
  }
}

/** Shape of a single dashboard card, matching {@link HealthDashboardCard}'s props. */
interface CardModel {
  key: string
  title: string
  value: string | null
  noDataLabel: string
  subtitle?: string | null
  targetDisplayValue?: string | null
  noTargetLabel?: string | null
  footerText?: string | null
  arrowDirection?: 'up' | 'down' | null
}

/** The nine dashboard cards, derived from the dashboard stats and targets. */
const cards = computed<CardModel[]>(() => {
  const d = dashboard.value
  const tg = targets.value
  const u = units.value
  const noData = t('health.dashboard.labelNoData')
  const fastingSeconds = d?.fasting ? fastingElapsedSeconds(d.fasting) : null
  const bmi = d?.bmi ?? null

  return [
    {
      key: 'sleep',
      title: t('health.dashboard.sleep'),
      value: d?.sleepSeconds != null ? formatHoursMinutes(d.sleepSeconds) : null,
      noDataLabel: noData,
      noTargetLabel: t('health.dashboard.noSleepTarget'),
      targetDisplayValue: tg?.sleepSeconds != null ? formatHoursMinutes(tg.sleepSeconds) : null,
      arrowDirection: arrow(d?.sleepSeconds ?? null, tg?.sleepSeconds ?? null),
    },
    {
      key: 'rhr',
      title: t('health.dashboard.restingHeartRate'),
      value: d?.restingHeartRate != null ? formatRestingHeartRate(d.restingHeartRate) : null,
      noDataLabel: noData,
      footerText: hrvLabel(d?.hrvStatus ?? null),
    },
    {
      key: 'skinTemp',
      title: t('health.dashboard.avgSkinTemperatureDeviation'),
      value: d?.skinTempDeviation != null ? formatSkinTempDeviation(d.skinTempDeviation) : null,
      noDataLabel: noData,
    },
    {
      key: 'weight',
      title: t('health.dashboard.weight'),
      value: d?.weightKg != null ? formatWeight(d.weightKg, u) : null,
      noDataLabel: noData,
      noTargetLabel: t('health.dashboard.noWeightTarget'),
      targetDisplayValue: tg?.weightKg != null ? formatWeight(tg.weightKg, u) : null,
      arrowDirection: arrow(d?.weightKg ?? null, tg?.weightKg ?? null),
    },
    {
      key: 'bmi',
      title: t('health.dashboard.bmi'),
      value: bmi != null ? formatBmi(bmi) : null,
      noDataLabel: t('health.dashboard.noWeightData'),
      footerText: bmiLabel(bmi),
    },
    {
      key: 'steps',
      title: t('health.dashboard.steps'),
      value: d?.steps != null ? formatSteps(d.steps) : null,
      noDataLabel: noData,
      noTargetLabel: t('health.dashboard.noStepsTarget'),
      targetDisplayValue:
        tg?.steps != null
          ? `${formatSteps(tg.steps)} ${t('health.dashboard.stepsTargetLabel')}`
          : null,
      arrowDirection: arrow(d?.steps ?? null, tg?.steps ?? null),
    },
    {
      key: 'fasting',
      title: t('health.dashboard.fasting'),
      value: fastingSeconds != null ? formatHoursMinutes(fastingSeconds) : null,
      noDataLabel: noData,
      noTargetLabel: t('health.dashboard.noFastingTarget'),
      targetDisplayValue: tg?.fastingSeconds != null ? formatHoursMinutes(tg.fastingSeconds) : null,
      arrowDirection: arrow(fastingSeconds, tg?.fastingSeconds ?? null),
    },
    {
      key: 'water',
      title: t('health.dashboard.water'),
      value: d?.waterMl != null ? formatWater(d.waterMl, u) : null,
      noDataLabel: noData,
      noTargetLabel: t('health.dashboard.noWaterTarget'),
      targetDisplayValue: tg?.waterMl != null ? formatWater(tg.waterMl, u) : null,
      arrowDirection: arrow(d?.waterMl ?? null, tg?.waterMl ?? null),
    },
    {
      key: 'poop',
      title: t('health.dashboard.poop'),
      value: d?.poopCount != null ? String(d.poopCount) : null,
      noDataLabel: noData,
      noTargetLabel: t('health.dashboard.noPoopTarget'),
      targetDisplayValue:
        tg?.poopCount != null ? `${tg.poopCount} ${t('health.dashboard.poopTargetLabel')}` : null,
      arrowDirection: arrow(d?.poopCount ?? null, tg?.poopCount ?? null),
    },
  ]
})
</script>

<template>
  <div class="flex flex-col gap-3">
    <header class="flex flex-col gap-1">
      <h1 class="text-page-title">{{ t('health.dashboard.title') }}</h1>
      <p class="text-body">{{ t('health.dashboard.subtitle') }}</p>
    </header>
    <Card v-if="isError">
      <ErrorState
        :title="t('health.dashboard.errorTitle')"
        :description="t('health.dashboard.errorDescription')"
        @retry="refetch"
      >
        <template #action="{ retry }">
          <Button variant="outline" size="sm" @click="retry">
            {{ t('health.dashboard.retry') }}
          </Button>
        </template>
      </ErrorState>
    </Card>

    <div v-else class="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
      <HealthDashboardCard
        v-for="card in cards"
        :key="card.key"
        :title="card.title"
        :value="card.value"
        :no-data-label="card.noDataLabel"
        :is-loading="isLoading"
        :subtitle="card.subtitle"
        :target-display-value="card.targetDisplayValue"
        :no-target-label="card.noTargetLabel"
        :footer-text="card.footerText"
        :arrow-direction="card.arrowDirection"
      />
    </div>
  </div>
</template>
