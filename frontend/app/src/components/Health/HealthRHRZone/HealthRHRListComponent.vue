<template>
  <li class="list-group-item d-flex justify-content-between p-0 bg-body-tertiary">
    <div class="d-flex align-items-center">
      <div>
        <div class="fw-bold">
          <span>{{ userHealthSleep.resting_heart_rate }} {{ $t('generalItems.unitsBpm') }}</span>
        </div>
        <span>
          {{ $t('healthStepsListComponent.labelDate') }}:
          {{ formatDateShort(userHealthSleep.date) }}
        </span>
      </div>
    </div>
    <div>
      <span class="align-middle me-3 d-none d-sm-inline" v-if="userHealthSleep.source === 'garmin'">
        <img :src="INTEGRATION_LOGOS.garminConnectApp" alt="Garmin Connect logo" height="22" />
      </span>
    </div>
  </li>
</template>

<script setup>
import { useI18n } from 'vue-i18n'
// Import constants
import { INTEGRATION_LOGOS } from '@/constants/integrationLogoConstants'

import { formatDateShort } from '@/utils/dateTimeUtils'

const props = defineProps({
  userHealthSleep: {
    type: Object,
    required: true
  }
})

const { t } = useI18n()
</script>
