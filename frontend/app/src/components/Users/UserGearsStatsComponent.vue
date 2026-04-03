<template>
  <h5>{{ t('userGearsStatsComponent.title') }}</h5>
  <ul class="list-group list-group-flush" v-if="gears && gears.length">
    <li
      v-for="gear in gears"
      :key="gear.id"
      class="list-group-item d-flex justify-content-between px-0 bg-body-tertiary"
    >
      <div class="d-flex align-items-center">
        <img
          :src="getGearAvatar(gear.gear_type)"
          :alt="getGearTypeName(gear.gear_type)"
          width="40"
          height="40"
          class="rounded-circle me-3"
        />
        <div>
          <div class="fw-bold">{{ gear.nickname }}</div>
          <small class="text-muted">
            {{ formatDistance(gear.total_distance) }}
          </small>
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
import { getGearAvatar } from '@/constants/gearAvatarConstants'

import NoItemsFoundComponents from '@/components/GeneralComponents/NoItemsFoundComponents.vue'

const props = defineProps({
  gears: {
    type: [Array, null],
    required: true
  }
})

const { t } = useI18n()
const authStore = useAuthStore()

function formatDistance(distance) {
  return formatDistanceRaw(t, distance, authStore.user.units, false)
}

function getGearTypeName(gearType) {
  const gearTypeNames = {
    1: t('gearsListComponent.gearListTypeOption1'),
    2: t('gearsListComponent.gearListTypeOption2'),
    3: t('gearsListComponent.gearListTypeOption3'),
    4: t('gearsListComponent.gearListTypeOption4'),
    5: t('gearsListComponent.gearListTypeOption5'),
    6: t('gearsListComponent.gearListTypeOption6'),
    7: t('gearsListComponent.gearListTypeOption7'),
    8: t('gearsListComponent.gearListTypeOption8')
  }
  return gearTypeNames[gearType] || gearTypeNames[8]
}
</script>
