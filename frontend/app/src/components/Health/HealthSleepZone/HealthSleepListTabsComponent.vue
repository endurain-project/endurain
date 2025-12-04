<template>
  <!-- Bootstrap Tabs Navigation -->
  <ul class="nav nav-tabs mt-3" role="tablist">
    <li class="nav-item" role="presentation">
      <button class="nav-link active link-body-emphasis link-underline-opacity-0 link-underline-opacity-100-hover"
        :id="`sleep-score-tab-${userHealthSleep.id}`" data-bs-toggle="tab"
        :data-bs-target="`#sleep-score-${userHealthSleep.id}`" type="button" role="tab"
        :aria-controls="`sleep-score-${userHealthSleep.id}`" aria-selected="true">
        {{ $t('healthSleepListTabsComponent.sleepScoreLabel') }}
      </button>
    </li>
    <li class="nav-item" role="presentation">
      <button class="nav-link link-body-emphasis link-underline-opacity-0 link-underline-opacity-100-hover"
        :id="`sleep-details-tab-${userHealthSleep.id}`" data-bs-toggle="tab"
        :data-bs-target="`#sleep-details-${userHealthSleep.id}`" type="button" role="tab"
        :aria-controls="`sleep-details-${userHealthSleep.id}`" aria-selected="false">
        {{ $t('healthSleepListTabsComponent.sleepDetailsLabel') }}
      </button>
    </li>
  </ul>

  <!-- Tab Content -->
  <div class="tab-content mt-3">
    <!-- Score tab -->
    <div class="tab-pane fade show active" :id="`sleep-score-${userHealthSleep.id}`" role="tabpanel"
      :aria-labelledby="`sleep-score-tab-${userHealthSleep.id}`">
      <!-- Sleep summary -->
      <section class="pb-3 mb-3 border-bottom">
        <h6 class="fw-semibold mb-2">
          {{ $t('healthSleepListTabsComponent.summaryTitle') }}
        </h6>
        <div class="row">
          <div class="col-12 col-md-6">
            <!-- sleep_score_overall -->
            <p class="mb-1">
              <span class="fw-semibold">
                {{ $t('healthSleepListTabsComponent.scoreLabel') }}:
              </span>
              <span v-if="userHealthSleep.sleep_score_overall">{{ userHealthSleep.sleep_score_overall }}</span>
              <span v-else>{{ $t('generalItems.labelNoData') }}</span>
            </p>
            <!-- sleep_score_quality -->
            <p class="mb-1">
              <span class="fw-semibold">
                {{ $t('healthSleepListTabsComponent.qualityLabel') }}:
              </span>
              <span v-if="userHealthSleep.sleep_score_quality">{{
                $t(getScoreStatusI18nKey(userHealthSleep.sleep_score_quality)) }}</span>
              <span v-else>{{ $t('generalItems.labelNoData') }}</span>
            </p>
          </div>

          <div class="col-12 col-md-6">
            <!-- sleep_score_duration-->
            <p class="mb-1">
              <span class="fw-semibold">
                {{ $t('healthSleepListTabsComponent.durationLabel') }}:
              </span>
              <span v-if="userHealthSleep.sleep_score_duration">{{
                $t(getScoreStatusI18nKey(userHealthSleep.sleep_score_duration)) }}</span>
              <span v-else>{{ $t('generalItems.labelNoData') }}</span>
            </p>
            <!-- hrv_status -->
            <p class="mb-0">
              <span class="fw-semibold">
                {{ $t('healthSleepListTabsComponent.HRVLabel') }}:
              </span>
              <span v-if="userHealthSleep.hrv_status">{{ $t(getHrvStatusI18nKey(userHealthSleep.hrv_status)) }}</span>
              <span v-else>{{ $t('generalItems.labelNoData') }}</span>
            </p>
          </div>
        </div>
      </section>

      <!-- Breakdown -->
      <section class="pb-3 mb-3 border-bottom">
        <h6 class="fw-semibold mb-2">
          {{ $t('healthSleepListTabsComponent.breakdownTitle') }}
        </h6>
        <div class="row">
          <div class="col-12 col-md-6">
            <!-- deep_sleep_seconds -->
            <p class="mb-1">
              <span class="fw-semibold">
                {{ $t('healthSleepListTabsComponent.deepLabel') }}:
              </span>
              <span v-if="userHealthSleep.deep_sleep_seconds">
                {{ formatDuration(userHealthSleep.deep_sleep_seconds) }}
                -
                {{ $t(getScoreStatusI18nKey(userHealthSleep.deep_percentage_score)) }}
              </span>
              <span v-else>{{ $t('generalItems.labelNoData') }}</span>
            </p>
            <!-- rem_sleep_seconds-->
            <p class="mb-1">
              <span class="fw-semibold">
                {{ $t('healthSleepListTabsComponent.REMLabel') }}:
              </span>
              <span v-if="userHealthSleep.rem_sleep_seconds">
                {{ formatDuration(userHealthSleep.rem_sleep_seconds) }}
                -
                {{ $t(getScoreStatusI18nKey(userHealthSleep.rem_percentage_score)) }}
              </span>
              <span v-else>{{ $t('generalItems.labelNoData') }}</span>
            </p>
          </div>

          <div class="col-12 col-md-6">
            <!-- light_sleep_seconds -->
            <p class="mb-1">
              <span class="fw-semibold">
                {{ $t('healthSleepListTabsComponent.lightLabel') }}:
              </span>
              <span v-if="userHealthSleep.light_sleep_seconds">
                {{ formatDuration(userHealthSleep.light_sleep_seconds) }}
                -
                {{ $t(getScoreStatusI18nKey(userHealthSleep.light_percentage_score)) }}
              </span>
              <span v-else>{{ $t('generalItems.labelNoData') }}</span>
            </p>
            <!-- awake_sleep_seconds -->
            <p class="mb-1">
              <span class="fw-semibold">
                {{ $t('healthSleepListTabsComponent.awakeLabel') }}:
              </span>
              <span v-if="userHealthSleep.awake_sleep_seconds">
                {{ formatDuration(userHealthSleep.awake_sleep_seconds) }}
                -
                {{ $t(getScoreStatusI18nKey(userHealthSleep.awake_count_score)) }}
              </span>
              <span v-else>{{ $t('generalItems.labelNoData') }}</span>
            </p>
          </div>
        </div>
      </section>
    </div>

    <!-- Sleep Details Tab -->
    <div class="tab-pane fade" :id="`sleep-details-${userHealthSleep.id}`" role="tabpanel"
      :aria-labelledby="`sleep-details-tab-${userHealthSleep.id}`">
      <!-- Heart Rate -->
      <section class="pb-3 mb-3 border-bottom">
        <div class="row">
          <div class="col-12 col-md-6">
            <!-- resting_heart_rate -->
            <p class="mb-1">
              <span class="fw-semibold">
                {{ $t('healthSleepListTabsComponent.restingHeartRateLabel') }}:
              </span>
              <span v-if="userHealthSleep.resting_heart_rate">
                {{ Number(userHealthSleep.resting_heart_rate) }} {{ $t('generalItems.unitsBpm') }}
              </span>
              <span v-else>{{ $t('generalItems.labelNoData') }}</span>
            </p>
            <!-- avg_skin_temp_deviation -->
            <p class="mb-1">
              <span class="fw-semibold">
                {{ $t('healthSleepListTabsComponent.avgSkinTempDeviationLabel') }}:
              </span>
              <span v-if="userHealthSleep.avg_skin_temp_deviation">
                {{ parseFloat(userHealthSleep.avg_skin_temp_deviation) }} {{ $t('generalItems.unitsCelsius') }}
              </span>
              <span v-else>{{ $t('generalItems.labelNoData') }}</span>
            </p>
          </div>
          <div class="col-12 col-md-6">
            <!-- avg_sleep_stress -->
            <p class="mb-1">
              <span class="fw-semibold">
                {{ $t('healthSleepListTabsComponent.avgSleepStressLabel') }}:
              </span>
              <span v-if="userHealthSleep.avg_sleep_stress">
                {{ Number(userHealthSleep.avg_sleep_stress) }}
              </span>
              <span v-else>{{ $t('generalItems.labelNoData') }}</span>
            </p>
          </div>
        </div>
      </section>
      <!-- Heart Rate -->
      <section class="pb-3 mb-3 border-bottom">
        <h6 class="fw-semibold mb-2">
          {{ $t('healthSleepListTabsComponent.heartRateTitle') }}
        </h6>
        <div class="row">
          <div class="col-12 col-md-6">
            <!-- avg_heart_rate -->
            <p class="mb-1">
              <span class="fw-semibold">
                {{ $t('healthSleepListTabsComponent.avgLabel') }}:
              </span>
              <span v-if="userHealthSleep.avg_heart_rate">
                {{ Number(userHealthSleep.avg_heart_rate) }} {{ $t('generalItems.unitsBpm') }}
              </span>
              <span v-else>{{ $t('generalItems.labelNoData') }}</span>
            </p>
            <!-- max_heart_rate -->
            <p class="mb-1">
              <span class="fw-semibold">
                {{ $t('healthSleepListTabsComponent.maxLabel') }}:
              </span>
              <span v-if="userHealthSleep.max_heart_rate">
                {{ Number(userHealthSleep.max_heart_rate) }} {{ $t('generalItems.unitsBrpm') }}
              </span>
              <span v-else>{{ $t('generalItems.labelNoData') }}</span>
            </p>
          </div>
          <div class="col-12 col-md-6">
            <!-- min_heart_rate -->
            <p class="mb-1">
              <span class="fw-semibold">
                {{ $t('healthSleepListTabsComponent.minLabel') }}:
              </span>
              <span v-if="userHealthSleep.min_heart_rate">
                {{ Number(userHealthSleep.min_heart_rate) }} {{ $t('generalItems.unitsBrpm') }}
              </span>
              <span v-else>{{ $t('generalItems.labelNoData') }}</span>
            </p>
          </div>
        </div>
      </section>

      <!-- SpO2 -->
      <section class="pb-3 mb-3 border-bottom">
        <h6 class="fw-semibold mb-2">
          {{ $t('healthSleepListTabsComponent.spo2Title') }}
        </h6>
        <div class="row">
          <div class="col-12 col-md-6">
            <!-- avg_spo2 -->
            <p class="mb-1">
              <span class="fw-semibold">
                {{ $t('healthSleepListTabsComponent.avgLabel') }}:
              </span>
              <span v-if="userHealthSleep.avg_spo2">
                {{ Number(userHealthSleep.avg_spo2) }}%
              </span>
              <span v-else>{{ $t('generalItems.labelNoData') }}</span>
            </p>
            <!-- highest_spo2 -->
            <p class="mb-1">
              <span class="fw-semibold">
                {{ $t('healthSleepListTabsComponent.maxLabel') }}:
              </span>
              <span v-if="userHealthSleep.highest_spo2">
                {{ Number(userHealthSleep.highest_spo2) }}%
              </span>
              <span v-else>{{ $t('generalItems.labelNoData') }}</span>
            </p>
          </div>
          <div class="col-12 col-md-6">
            <!-- lowest_spo2 -->
            <p class="mb-1">
              <span class="fw-semibold">
                {{ $t('healthSleepListTabsComponent.minLabel') }}:
              </span>
              <span v-if="userHealthSleep.lowest_spo2">
                {{ Number(userHealthSleep.lowest_spo2) }}%
              </span>
              <span v-else>{{ $t('generalItems.labelNoData') }}</span>
            </p>
          </div>
        </div>
      </section>

      <!-- Respiratory Rate -->
      <section class="pb-3 mb-3 border-bottom">
        <h6 class="fw-semibold mb-2">
          {{ $t('healthSleepListTabsComponent.respiratoryTitle') }}
        </h6>
        <div class="row">
          <div class="col-12 col-md-6">
            <!-- avg_respiration -->
            <p class="mb-1">
              <span class="fw-semibold">
                {{ $t('healthSleepListTabsComponent.avgLabel') }}:
              </span>
              <span v-if="userHealthSleep.avg_respiration">
                {{ Number(userHealthSleep.avg_respiration) }} {{ $t('generalItems.unitsBrpm') }}
              </span>
              <span v-else>{{ $t('generalItems.labelNoData') }}</span>
            </p>
            <!-- highest_respiration -->
            <p class="mb-1">
              <span class="fw-semibold">
                {{ $t('healthSleepListTabsComponent.maxLabel') }}:
              </span>
              <span v-if="userHealthSleep.highest_respiration">
                {{ Number(userHealthSleep.highest_respiration) }} {{ $t('generalItems.unitsBrpm') }}
              </span>
              <span v-else>{{ $t('generalItems.labelNoData') }}</span>
            </p>
          </div>
          <div class="col-12 col-md-6">
            <!-- lowest_respiration -->
            <p class="mb-1">
              <span class="fw-semibold">
                {{ $t('healthSleepListTabsComponent.minLabel') }}:
              </span>
              <span v-if="userHealthSleep.lowest_respiration">
                {{ Number(userHealthSleep.lowest_respiration) }} {{ $t('generalItems.unitsBrpm') }}
              </span>
              <span v-else>{{ $t('generalItems.labelNoData') }}</span>
            </p>
          </div>
        </div>
      </section>
    </div>
  </div>
</template>

<script setup>
import { formatDuration } from '@/utils/dateTimeUtils'
import { getHrvStatusI18nKey, getScoreStatusI18nKey } from '@/utils/healthUtils'

const props = defineProps({
  userHealthSleep: {
    type: Object,
    required: true
  }
})

</script>