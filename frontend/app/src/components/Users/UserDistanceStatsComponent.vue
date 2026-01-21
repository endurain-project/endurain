<template>
  <div class="text-center">
    <span>{{ $t('userDistanceStats.thisWeekDistancesTitle') }}</span>
  </div>
  <div class="row mt-3 text-center">
    <!-- this week col one -->
    <div class="col">
      <!--<span class="fw-lighter">{{ thisWeek[0].translatedName }}</span>-->
      <font-awesome-icon :icon="['fas', thisWeek[0].icon]" size="2x" />
      <br />
      {{
        thisWeek && thisWeek[0].distance
          ? Math.floor(
              thisWeek[0].useMeters && authStore?.user?.units === 'metric'
                ? kmToMeters(thisWeek[0].distance)
                : thisWeek[0].distance
            ) + ' '
          : '0'
      }}
      <span v-if="authStore?.user?.units === 'metric'">
        <span v-if="thisWeek[0].useMeters">
          {{ $t('generalItems.unitsM') }}
        </span>
        <span v-else>
          {{ $t('generalItems.unitsKm') }}
        </span>
      </span>
      <span v-else>
        <span v-if="thisWeek[0].useMeters">
          {{ $t('generalItems.unitsYards') }}
        </span>
        <span v-else>
          {{ $t('generalItems.unitsMiles') }}
        </span>
      </span>
    </div>
    <!-- this week col two -->
    <div class="col">
      <font-awesome-icon :icon="['fas', thisWeek[1].icon]" size="2x" />
      <br />
      {{
        thisWeek && thisWeek[1].distance
          ? Math.floor(
              thisWeek[1].useMeters && authStore?.user?.units === 'metric'
                ? kmToMeters(thisWeek[1].distance)
                : thisWeek[1].distance
            ) + ' '
          : '0'
      }}
      <span v-if="authStore?.user?.units === 'metric'">
        <span v-if="thisWeek[1].useMeters">
          {{ $t('generalItems.unitsM') }}
        </span>
        <span v-else>
          {{ $t('generalItems.unitsKm') }}
        </span>
      </span>
      <span v-else>
        <span v-if="thisWeek[1].useMeters">
          {{ $t('generalItems.unitsYards') }}
        </span>
        <span v-else>
          {{ $t('generalItems.unitsMiles') }}
        </span>
      </span>
    </div>
    <!-- this week col three -->
    <div class="col">
      <font-awesome-icon :icon="['fas', thisWeek[2].icon]" size="2x" />
      <br />
      {{
        thisWeek && thisWeek[2].distance
          ? Math.floor(
              thisWeek[2].useMeters && authStore?.user?.units === 'metric'
                ? kmToMeters(thisWeek[2].distance)
                : thisWeek[2].distance
            ) + ' '
          : '0'
      }}
      <span v-if="authStore?.user?.units === 'metric'">
        <span v-if="thisWeek[2].useMeters">
          {{ $t('generalItems.unitsM') }}
        </span>
        <span v-else>
          {{ $t('generalItems.unitsKm') }}
        </span>
      </span>
      <span v-else>
        <span v-if="thisWeek[2].useMeters">
          {{ $t('generalItems.unitsYards') }}
        </span>
        <span v-else>
          {{ $t('generalItems.unitsMiles') }}
        </span>
      </span>
    </div>
  </div>

  <hr />

  <div class="text-center">
    <span>{{ $t('userDistanceStats.thisMonthDistancesTitle') }}</span>
  </div>
  <div class="row mt-3 text-center">
    <!-- this month col one -->
    <div class="col">
      <!--<span class="fw-lighter">{{ thisMonth[0].translatedName }}</span>-->
      <font-awesome-icon :icon="['fas', thisMonth[0].icon]" size="2x" />
      <br />
      {{
        thisMonth && thisMonth[0].distance
          ? Math.floor(
              thisMonth[0].useMeters && authStore?.user?.units === 'metric'
                ? kmToMeters(thisMonth[0].distance)
                : thisMonth[0].distance
            ) + ' '
          : '0'
      }}
      <span v-if="authStore?.user?.units === 'metric'">
        <span v-if="thisMonth[0].useMeters">
          {{ $t('generalItems.unitsM') }}
        </span>
        <span v-else>
          {{ $t('generalItems.unitsKm') }}
        </span>
      </span>
      <span v-else>
        <span v-if="thisMonth[0].useMeters">
          {{ $t('generalItems.unitsYards') }}
        </span>
        <span v-else>
          {{ $t('generalItems.unitsMiles') }}
        </span>
      </span>
    </div>
    <!-- this month col two -->
    <div class="col">
      <font-awesome-icon :icon="['fas', thisMonth[1].icon]" size="2x" />
      <br />
      {{
        thisMonth && thisMonth[1].distance
          ? Math.floor(
              thisMonth[1].useMeters && authStore?.user?.units === 'metric'
                ? kmToMeters(thisMonth[1].distance)
                : thisMonth[1].distance
            ) + ' '
          : '0'
      }}
      <span v-if="authStore?.user?.units === 'metric'">
        <span v-if="thisMonth[1].useMeters">
          {{ $t('generalItems.unitsM') }}
        </span>
        <span v-else>
          {{ $t('generalItems.unitsKm') }}
        </span>
      </span>
      <span v-else>
        <span v-if="thisMonth[1].useMeters">
          {{ $t('generalItems.unitsYards') }}
        </span>
        <span v-else>
          {{ $t('generalItems.unitsMiles') }}
        </span>
      </span>
    </div>
    <!-- this month col three -->
    <div class="col">
      <font-awesome-icon :icon="['fas', thisMonth[2].icon]" size="2x" />
      <br />
      {{
        thisMonth && thisMonth[2].distance
          ? Math.floor(
              thisMonth[2].useMeters && authStore?.user?.units === 'metric'
                ? kmToMeters(thisMonth[2].distance)
                : thisMonth[2].distance
            ) + ' '
          : '0'
      }}
      <span v-if="authStore?.user?.units === 'metric'">
        <span v-if="thisMonth[2].useMeters">
          {{ $t('generalItems.unitsM') }}
        </span>
        <span v-else>
          {{ $t('generalItems.unitsKm') }}
        </span>
      </span>
      <span v-else>
        <span v-if="thisMonth[2].useMeters">
          {{ $t('generalItems.unitsYards') }}
        </span>
        <span v-else>
          {{ $t('generalItems.unitsMiles') }}
        </span>
      </span>
    </div>
  </div>
</template>

<script setup>
// Importing the stores
import { computed } from 'vue'
import { useAuthStore } from '@/stores/authStore'
import { metersToKm, metersToMiles, metersToYards, kmToMeters } from '@/utils/unitsUtils'

const props = defineProps({
  thisWeekDistances: {
    type: Object,
    required: true
  },
  thisMonthDistances: {
    type: Object,
    required: true
  }
})

const authStore = useAuthStore()

const getTopThreeActivities = (distances) => {
  const convertDistanceMetersToKmsOrMiles = (distance) =>
    authStore?.user?.units === 'metric' ? metersToKm(distance) : metersToMiles(distance)
  const convertDistanceMetersToYards = (distance) =>
    authStore?.user?.units === 'metric' ? metersToKm(distance) : metersToYards(distance)

  const activities = [
    {
      name: 'run',
      icon: 'person-running',
      useMeters: false,
      distance: convertDistanceMetersToKmsOrMiles(distances.run)
    },
    {
      name: 'bike',
      icon: 'person-biking',
      useMeters: false,
      distance: convertDistanceMetersToKmsOrMiles(distances.bike)
    },
    {
      name: 'swim',
      icon: 'person-swimming',
      useMeters: true,
      distance: convertDistanceMetersToYards(distances.swim)
    },
    {
      name: 'walk',
      icon: 'person-walking',
      useMeters: false,
      distance: convertDistanceMetersToKmsOrMiles(distances.walk)
    },
    {
      name: 'hike',
      icon: 'person-hiking',
      useMeters: false,
      distance: convertDistanceMetersToKmsOrMiles(distances.hike)
    },
    {
      name: 'rowing',
      icon: 'sailboat',
      useMeters: false,
      distance: convertDistanceMetersToKmsOrMiles(distances.rowing)
    },
    {
      name: 'snow_ski',
      icon: 'person-skiing',
      useMeters: false,
      distance: convertDistanceMetersToKmsOrMiles(distances.ski)
    },
    {
      name: 'snowboard',
      icon: 'person-snowboarding',
      useMeters: false,
      distance: convertDistanceMetersToKmsOrMiles(distances.snowboard)
    },
    {
      name: 'windsurf',
      icon: 'wind',
      useMeters: false,
      distance: convertDistanceMetersToKmsOrMiles(distances.windsurf)
    }
  ]
  // Sort activities by distance
  const sortedActivities = activities.sort((a, b) => b.distance - a.distance)
  // Return top 3 activities
  return sortedActivities.slice(0, 3)
}

const thisWeek = computed(() => getTopThreeActivities(props.thisWeekDistances))
const thisMonth = computed(() => getTopThreeActivities(props.thisMonthDistances))
</script>
