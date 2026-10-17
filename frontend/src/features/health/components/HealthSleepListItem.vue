<script setup lang="ts">
import { computed, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { ChevronDown, Pencil, Trash2 } from '@lucide/vue'

import type { SleepEntry } from '@/features/health/types'

import { Button } from '@/components/ui/button'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { INTEGRATION_LOGOS } from '@/constants/integrationLogos'
import {
  formatHealthEntryDate,
  formatHoursMinutes,
  formatRestingHeartRate,
  formatSkinTempDeviation,
  hrvStatusKey,
  sleepScoreKey,
} from '@/features/health/utils/healthFormat'

import HealthSleepHypnogram from './HealthSleepHypnogram.vue'

const props = defineProps<{
  /** The sleep entry to render. */
  entry: SleepEntry
}>()
const emit = defineEmits<{ edit: [entry: SleepEntry]; delete: [entry: SleepEntry] }>()

const { t, locale } = useI18n()

const expanded = ref(false)

/** Resolves a sleep score string to a localized label, or `null` when absent. */
function scoreText(score: string | null): string | null {
  if (score === null) return null
  const key = sleepScoreKey(score)
  return key ? t(`health.sleep.${key}`) : score
}

/** Stage-duration breakdown rows paired with their percentage sub-score. */
const stageBreakdown = computed(() =>
  [
    { key: 'deep', seconds: props.entry.deepSleepSeconds, score: props.entry.deepPercentageScore },
    {
      key: 'light',
      seconds: props.entry.lightSleepSeconds,
      score: props.entry.lightPercentageScore,
    },
    { key: 'rem', seconds: props.entry.remSleepSeconds, score: props.entry.remPercentageScore },
    { key: 'awake', seconds: props.entry.awakeSleepSeconds, score: props.entry.awakeCountScore },
  ].filter((row) => row.seconds !== null || row.score !== null),
)

/** Whether the Score tab has anything to show. */
const hasScoreContent = computed(
  () =>
    props.entry.sleepScoreOverall !== null ||
    props.entry.sleepScoreQuality !== null ||
    props.entry.sleepScoreDuration !== null ||
    props.entry.hrvStatus !== null ||
    stageBreakdown.value.length > 0,
)

/** Whether the Details tab has anything to show. */
const hasDetailContent = computed(
  () =>
    props.entry.restingHeartRate !== null ||
    props.entry.avgSkinTempDeviation !== null ||
    props.entry.avgSleepStress !== null ||
    props.entry.awakeCount !== null ||
    props.entry.avgHeartRate !== null ||
    props.entry.minHeartRate !== null ||
    props.entry.maxHeartRate !== null ||
    props.entry.avgSpo2 !== null ||
    props.entry.lowestSpo2 !== null ||
    props.entry.highestSpo2 !== null ||
    props.entry.avgRespiration !== null ||
    props.entry.lowestRespiration !== null ||
    props.entry.highestRespiration !== null,
)

/** Whether the Summary area (sleep-score sub-metrics) has anything to show. */
const hasSummaryContent = computed(
  () =>
    props.entry.sleepScoreOverall !== null ||
    props.entry.sleepScoreQuality !== null ||
    props.entry.sleepScoreDuration !== null ||
    props.entry.hrvStatus !== null,
)

/** Whether the Overview area (general night metrics) has anything to show. */
const hasOverviewContent = computed(
  () =>
    props.entry.restingHeartRate !== null ||
    props.entry.avgSkinTempDeviation !== null ||
    props.entry.avgSleepStress !== null ||
    props.entry.awakeCount !== null,
)

/** Whether the Heart rate area has anything to show. */
const hasHeartRateContent = computed(
  () =>
    props.entry.avgHeartRate !== null ||
    props.entry.minHeartRate !== null ||
    props.entry.maxHeartRate !== null,
)

/** Whether the Blood oxygen area has anything to show. */
const hasSpo2Content = computed(
  () =>
    props.entry.avgSpo2 !== null ||
    props.entry.lowestSpo2 !== null ||
    props.entry.highestSpo2 !== null,
)

/** Whether the Respiration area has anything to show. */
const hasRespirationContent = computed(
  () =>
    props.entry.avgRespiration !== null ||
    props.entry.lowestRespiration !== null ||
    props.entry.highestRespiration !== null,
)

/** Whether there is a stage timeline to draw. */
const hasHypnogram = computed(() => props.entry.sleepStages.length > 0)

/**
 * Minutes between the sleeper's wall clock and GMT for this night.
 *
 * Stage times are true GMT instants, while `sleepStartTimeLocal` holds the
 * sleeper's wall clock (Garmin's already offset-shifted epoch, surfaced as a
 * UTC-labelled value). Their difference is the recording offset — the only zone
 * signal a sleep entry carries — used to label the hypnogram axis in the
 * timezone the night was actually slept in rather than the viewer's.
 *
 * Rounded to a quarter hour to absorb the small skew between "sleep start" and
 * "first stage start"; every real UTC offset is a multiple of 15 minutes.
 */
const recordingOffsetMinutes = computed(() => {
  const local = props.entry.sleepStartTimeLocal
  const earliestStageGmt = props.entry.sleepStages
    .map((stage) => stage.startTimeGmt)
    .filter((value): value is string => Boolean(value))
    .sort()[0]
  if (!local || !earliestStageGmt) {
    return 0
  }
  const localMs = new Date(local).getTime()
  const gmtMs = new Date(earliestStageGmt).getTime()
  if (Number.isNaN(localMs) || Number.isNaN(gmtMs)) {
    return 0
  }
  return Math.round((localMs - gmtMs) / 900000) * 15
})

/** Whether any optional detail is present to reveal. */
const hasDetails = computed(
  () => hasScoreContent.value || hasDetailContent.value || hasHypnogram.value,
)

/** Primary sleep-duration string, or an em dash when no duration is recorded. */
const durationLabel = computed(() =>
  props.entry.totalSleepSeconds === null ? '—' : formatHoursMinutes(props.entry.totalSleepSeconds),
)

const dateLabel = computed(() => formatHealthEntryDate(props.entry.date, locale.value))
const fromGarmin = computed(() => props.entry.source === 'garmin')

/** Resolves the HRV status to a localized label, or `null` when unrecognised. */
const hrvLabel = computed(() => {
  if (props.entry.hrvStatus === null) {
    return null
  }
  const key = hrvStatusKey(props.entry.hrvStatus)
  return key ? t(`health.sleep.${key}`) : props.entry.hrvStatus
})
</script>

<template>
  <div class="px-4 py-3">
    <div class="flex items-center justify-between gap-3">
      <div class="flex min-w-0 items-center gap-2">
        <p class="text-item-title">{{ durationLabel }}</p>
        <span v-if="entry.sleepScoreOverall !== null" class="text-caption">
          {{ t('health.sleep.score') }} {{ entry.sleepScoreOverall }}
        </span>
      </div>
      <div class="flex shrink-0 items-center gap-1">
        <Button
          v-if="hasDetails"
          variant="ghost"
          size="icon-sm"
          :aria-label="t('health.sleep.toggleDetails')"
          :aria-expanded="expanded"
          @click="expanded = !expanded"
        >
          <ChevronDown
            class="size-4 transition-transform"
            :class="{ 'rotate-180': expanded }"
            aria-hidden="true"
          />
        </Button>
        <img
          v-if="fromGarmin"
          :src="INTEGRATION_LOGOS.garminApp"
          :alt="t('health.sleep.sourceGarmin')"
          :title="t('health.sleep.sourceGarmin')"
          class="size-4 shrink-0"
        />
        <Button
          variant="ghost"
          size="icon-sm"
          :aria-label="t('health.sleep.actions.edit')"
          @click="emit('edit', entry)"
        >
          <Pencil class="size-4" aria-hidden="true" />
        </Button>
        <Button
          variant="ghostDestructive"
          size="icon-sm"
          :aria-label="t('health.sleep.actions.delete')"
          @click="emit('delete', entry)"
        >
          <Trash2 class="size-4" aria-hidden="true" />
        </Button>
      </div>
    </div>
    <p class="text-hint">{{ dateLabel }}</p>
    <div v-if="hasDetails && expanded" class="mt-3 flex flex-col gap-3">
      <Tabs default-value="score">
        <TabsList class="grid w-full grid-cols-2" :aria-label="t('health.sleep.detail.tabsLabel')">
          <TabsTrigger value="score">{{ t('health.sleep.detail.tabScore') }}</TabsTrigger>
          <TabsTrigger value="details">{{ t('health.sleep.detail.tabDetails') }}</TabsTrigger>
        </TabsList>
        <TabsContent value="score" class="mt-3">
          <div v-if="hasScoreContent" class="divide-y divide-border">
            <div v-if="hasSummaryContent" class="py-3 first:pt-0 last:pb-0">
              <p class="text-item-title mb-2">{{ t('health.sleep.detail.summary') }}</p>
              <dl class="grid grid-cols-2 gap-x-4 gap-y-2 sm:grid-cols-3">
                <div v-if="entry.sleepScoreOverall !== null">
                  <dt class="text-caption">{{ t('health.sleep.detail.score') }}</dt>
                  <dd class="text-hint">{{ entry.sleepScoreOverall }}</dd>
                </div>
                <div v-if="scoreText(entry.sleepScoreQuality)">
                  <dt class="text-caption">{{ t('health.sleep.detail.quality') }}</dt>
                  <dd class="text-hint">{{ scoreText(entry.sleepScoreQuality) }}</dd>
                </div>
                <div v-if="scoreText(entry.sleepScoreDuration)">
                  <dt class="text-caption">{{ t('health.sleep.detail.duration') }}</dt>
                  <dd class="text-hint">{{ scoreText(entry.sleepScoreDuration) }}</dd>
                </div>
                <div v-if="hrvLabel !== null">
                  <dt class="text-caption">{{ t('health.sleep.detail.hrv') }}</dt>
                  <dd class="text-hint">{{ hrvLabel }}</dd>
                </div>
              </dl>
            </div>
            <div v-if="stageBreakdown.length > 0" class="py-3 first:pt-0 last:pb-0">
              <p class="text-item-title mb-2">{{ t('health.sleep.detail.breakdown') }}</p>
              <dl class="grid grid-cols-2 gap-x-4 gap-y-2 sm:grid-cols-3">
                <div v-for="row in stageBreakdown" :key="row.key">
                  <dt class="text-caption">{{ t(`health.sleep.detail.${row.key}`) }}</dt>
                  <dd class="text-hint">
                    <span v-if="row.seconds !== null">{{ formatHoursMinutes(row.seconds) }}</span>
                    <span v-else>—</span>
                    <span v-if="scoreText(row.score)" class="text-muted-foreground">
                      · {{ scoreText(row.score) }}</span
                    >
                  </dd>
                </div>
              </dl>
            </div>
          </div>
          <p v-else class="text-hint">{{ t('health.sleep.detail.noData') }}</p>
        </TabsContent>
        <TabsContent value="details" class="mt-3">
          <div v-if="hasDetailContent" class="divide-y divide-border">
            <div v-if="hasOverviewContent" class="py-3 first:pt-0 last:pb-0">
              <p class="text-item-title mb-2">{{ t('health.sleep.detail.overview') }}</p>
              <dl class="grid grid-cols-2 gap-x-4 gap-y-2 sm:grid-cols-3">
                <div v-if="entry.restingHeartRate !== null">
                  <dt class="text-caption">{{ t('health.sleep.detail.restingHeartRate') }}</dt>
                  <dd class="text-hint">{{ formatRestingHeartRate(entry.restingHeartRate) }}</dd>
                </div>
                <div v-if="entry.avgSkinTempDeviation !== null">
                  <dt class="text-caption">{{ t('health.sleep.detail.skinTempDeviation') }}</dt>
                  <dd class="text-hint">
                    {{ formatSkinTempDeviation(entry.avgSkinTempDeviation) }}
                  </dd>
                </div>
                <div v-if="entry.avgSleepStress !== null">
                  <dt class="text-caption">{{ t('health.sleep.detail.avgSleepStress') }}</dt>
                  <dd class="text-hint">{{ entry.avgSleepStress }}</dd>
                </div>
                <div v-if="entry.awakeCount !== null">
                  <dt class="text-caption">{{ t('health.sleep.detail.awakeCount') }}</dt>
                  <dd class="text-hint">{{ entry.awakeCount }}</dd>
                </div>
              </dl>
            </div>
            <div v-if="hasHeartRateContent" class="py-3 first:pt-0 last:pb-0">
              <p class="text-item-title mb-2">{{ t('health.sleep.detail.heartRate') }}</p>
              <dl class="grid grid-cols-2 gap-x-4 gap-y-2 sm:grid-cols-3">
                <div v-if="entry.avgHeartRate !== null">
                  <dt class="text-caption">{{ t('health.sleep.detail.avg') }}</dt>
                  <dd class="text-hint">{{ formatRestingHeartRate(entry.avgHeartRate) }}</dd>
                </div>
                <div v-if="entry.minHeartRate !== null">
                  <dt class="text-caption">{{ t('health.sleep.detail.min') }}</dt>
                  <dd class="text-hint">{{ formatRestingHeartRate(entry.minHeartRate) }}</dd>
                </div>
                <div v-if="entry.maxHeartRate !== null">
                  <dt class="text-caption">{{ t('health.sleep.detail.max') }}</dt>
                  <dd class="text-hint">{{ formatRestingHeartRate(entry.maxHeartRate) }}</dd>
                </div>
              </dl>
            </div>
            <div v-if="hasSpo2Content" class="py-3 first:pt-0 last:pb-0">
              <p class="text-item-title mb-2">{{ t('health.sleep.detail.bloodOxygen') }}</p>
              <dl class="grid grid-cols-2 gap-x-4 gap-y-2 sm:grid-cols-3">
                <div v-if="entry.avgSpo2 !== null">
                  <dt class="text-caption">{{ t('health.sleep.detail.avg') }}</dt>
                  <dd class="text-hint">{{ entry.avgSpo2 }}%</dd>
                </div>
                <div v-if="entry.lowestSpo2 !== null">
                  <dt class="text-caption">{{ t('health.sleep.detail.min') }}</dt>
                  <dd class="text-hint">{{ entry.lowestSpo2 }}%</dd>
                </div>
                <div v-if="entry.highestSpo2 !== null">
                  <dt class="text-caption">{{ t('health.sleep.detail.max') }}</dt>
                  <dd class="text-hint">{{ entry.highestSpo2 }}%</dd>
                </div>
              </dl>
            </div>
            <div v-if="hasRespirationContent" class="py-3 first:pt-0 last:pb-0">
              <p class="text-item-title mb-2">{{ t('health.sleep.detail.respiration') }}</p>
              <dl class="grid grid-cols-2 gap-x-4 gap-y-2 sm:grid-cols-3">
                <div v-if="entry.avgRespiration !== null">
                  <dt class="text-caption">{{ t('health.sleep.detail.avg') }}</dt>
                  <dd class="text-hint">{{ entry.avgRespiration }}</dd>
                </div>
                <div v-if="entry.lowestRespiration !== null">
                  <dt class="text-caption">{{ t('health.sleep.detail.min') }}</dt>
                  <dd class="text-hint">{{ entry.lowestRespiration }}</dd>
                </div>
                <div v-if="entry.highestRespiration !== null">
                  <dt class="text-caption">{{ t('health.sleep.detail.max') }}</dt>
                  <dd class="text-hint">{{ entry.highestRespiration }}</dd>
                </div>
              </dl>
            </div>
          </div>
          <p v-else class="text-hint">{{ t('health.sleep.detail.noData') }}</p>
        </TabsContent>
      </Tabs>
      <HealthSleepHypnogram
        v-if="hasHypnogram"
        :stages="entry.sleepStages"
        :offset-minutes="recordingOffsetMinutes"
      />
    </div>
  </div>
</template>
