<template>
  <!-- Bootstrap Tabs Navigation -->
  <ul class="nav nav-tabs mt-3" role="tablist">
    <li class="nav-item" role="presentation">
      <button class="nav-link active link-body-emphasis link-underline-opacity-0 link-underline-opacity-100-hover"
        :id="`sessions-tab-${userHealthSleep.id}`" data-bs-toggle="tab"
        :data-bs-target="`#sessions-${userHealthSleep.id}`" type="button" role="tab"
        :aria-controls="`sessions-${userHealthSleep.id}`" aria-selected="true">
        {{ $t('healthSleepListTabsComponent.sleepScoreLabel') }}
      </button>
    </li>
    <li class="nav-item" role="presentation">
      <button class="nav-link link-body-emphasis link-underline-opacity-0 link-underline-opacity-100-hover"
        :id="`idps-tab-${userHealthSleep.id}`" data-bs-toggle="tab" :data-bs-target="`#idps-${userHealthSleep.id}`"
        type="button" role="tab" :aria-controls="`idps-${userHealthSleep.id}`" aria-selected="false">
        {{ $t('healthSleepListTabsComponent.sleepDetailsLabel') }}
      </button>
    </li>
  </ul>

  <!-- Tab Content -->
  <div class="tab-content mt-3">
    <!-- Score tab -->
    <div class="tab-pane fade show active" :id="`sessions-${userHealthSleep.id}`" role="tabpanel"
      :aria-labelledby="`sessions-tab-${userHealthSleep.id}`">
      <!-- Sleep summary -->
      <section class="pb-3 mb-3 border-bottom">
        <h6 class="fw-semibold mb-2">
          {{ $t('healthSleepListTabsComponent.summaryTitle') }}
        </h6>
        <div class="row">
          <div class="col-12 col-md-6">
            <p v-if="userHealthSleep.sleep_score_overall" class="mb-1">
              <span class="fw-semibold">
                {{ $t('healthSleepListTabsComponent.scoreLabel') }}:
              </span>
              {{ userHealthSleep.sleep_score_overall }}
            </p>
            <p v-if="userHealthSleep.sleep_score_quality" class="mb-1">
              <span class="fw-semibold">
                {{ $t('healthSleepListTabsComponent.qualityLabel') }}:
              </span>
              {{ $t(getScoreStatusI18nKey(userHealthSleep.sleep_score_quality)) }}
            </p>
          </div>

          <div class="col-12 col-md-6">
            <p v-if="userHealthSleep.sleep_score_duration" class="mb-1">
              <span class="fw-semibold">
                {{ $t('healthSleepListTabsComponent.durationLabel') }}:
              </span>
              {{ $t(getScoreStatusI18nKey(userHealthSleep.sleep_score_duration)) }}
            </p>
            <p v-if="userHealthSleep.hrv_status" class="mb-0">
              <span class="fw-semibold">
                {{ $t('healthSleepListTabsComponent.HRVLabel') }}:
              </span>
              {{ $t(getHrvStatusI18nKey(userHealthSleep.hrv_status)) }}
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
            <p class="mb-1">
              <span class="fw-semibold">
                {{ $t('healthSleepListTabsComponent.deepLabel') }}:
              </span>
              {{ formatDuration(userHealthSleep.deep_sleep_seconds) }}
              -
              {{ $t(getScoreStatusI18nKey(userHealthSleep.deep_percentage_score)) }}
            </p>
            <p class="mb-1">
              <span class="fw-semibold">
                {{ $t('healthSleepListTabsComponent.REMLabel') }}:
              </span>
              {{ formatDuration(userHealthSleep.rem_sleep_seconds) }}
              -
              {{ $t(getScoreStatusI18nKey(userHealthSleep.rem_percentage_score)) }}
            </p>
          </div>

          <div class="col-12 col-md-6">
            <p class="mb-1">
              <span class="fw-semibold">
                {{ $t('healthSleepListTabsComponent.lightLabel') }}:
              </span>
              {{ formatDuration(userHealthSleep.light_sleep_seconds) }}
              -
              {{ $t(getScoreStatusI18nKey(userHealthSleep.light_percentage_score)) }}
            </p>
            <p class="mb-1">
              <span class="fw-semibold">
                {{ $t('healthSleepListTabsComponent.awakeLabel') }}:
              </span>
              {{ formatDuration(userHealthSleep.awake_sleep_seconds) }}
              -
              {{ $t(getScoreStatusI18nKey(userHealthSleep.awake_count_score)) }}
            </p>
          </div>
        </div>
      </section>
    </div>
  </div>
</template>

<script setup>
import { formatDuration, formatDateShort } from '@/utils/dateTimeUtils'
import { getHrvStatusI18nKey, getScoreStatusI18nKey } from '@/utils/healthUtils'

const props = defineProps({
  userHealthSleep: {
    type: Object,
    required: true
  }
})

</script>