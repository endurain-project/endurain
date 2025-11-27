<template>
  <!-- Bootstrap Tabs Navigation -->
  <ul class="nav nav-tabs mt-3" role="tablist">
    <li class="nav-item" role="presentation">
      <button
        class="nav-link active link-body-emphasis link-underline-opacity-0 link-underline-opacity-100-hover"
        :id="`sessions-tab-${userHealthSleep.id}`"
        data-bs-toggle="tab"
        :data-bs-target="`#sessions-${userHealthSleep.id}`"
        type="button"
        role="tab"
        :aria-controls="`sessions-${userHealthSleep.id}`"
        aria-selected="true"
      >
        {{ $t('healthSleepListTabsComponent.sleepScoreLabel') }}
      </button>
    </li>
    <li class="nav-item" role="presentation">
      <button
        class="nav-link link-body-emphasis link-underline-opacity-0 link-underline-opacity-100-hover"
        :id="`idps-tab-${userHealthSleep.id}`"
        data-bs-toggle="tab"
        :data-bs-target="`#idps-${userHealthSleep.id}`"
        type="button"
        role="tab"
        :aria-controls="`idps-${userHealthSleep.id}`"
        aria-selected="false"
      >
        {{ $t('healthSleepListTabsComponent.sleepDetailsLabel') }}
      </button>
    </li>
  </ul>

  <!-- Tab Content -->
  <div class="tab-content mt-3">
    <!-- Score tab -->
    <div
      class="tab-pane fade show active"
      :id="`sessions-${userHealthSleep.id}`"
      role="tabpanel"
      :aria-labelledby="`sessions-tab-${userHealthSleep.id}`"
    >
      <div class="row">
        <div class="col">
          <p v-if="userHealthSleep.sleep_score_overall">{{ $t('healthSleepListTabsComponent.scoreLabel') }}: {{ userHealthSleep.sleep_score_overall }}</p>
          <p v-if="userHealthSleep.sleep_score_quality">{{ $t('healthSleepListTabsComponent.qualityLabel') }}: {{ userHealthSleep.sleep_score_quality }}</p>
          <p v-if="userHealthSleep.sleep_score_duration">{{ $t('healthSleepListTabsComponent.durationLabel') }}: {{ $t(getScoreStatusI18nKey(userHealthSleep.sleep_score_duration)) }}</p>
          <p v-if="userHealthSleep.hrv_status">
            HRV Status: {{ $t(getHrvStatusI18nKey(userHealthSleep.hrv_status)) }}
          </p>
        </div>
        <div class="col">
          <p>Deep: {{ formatDuration(userHealthSleep.deep_sleep_seconds) }}</p>
          <p>Light: {{ formatDuration(userHealthSleep.light_sleep_seconds) }}</p>
          <p>REM: {{ formatDuration(userHealthSleep.rem_sleep_seconds) }}</p>
          <p>Awake: {{ formatDuration(userHealthSleep.awake_sleep_seconds) }}</p>

        </div>
      </div>
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