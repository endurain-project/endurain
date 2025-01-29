<template>
    <div class="mb-3 mt-3">
        <span class="fw-lighter">{{ $t("userDistanceStats.thisWeekDistancesTitle") }}</span>
        <div class="row mb-3">
            <div class="col text-start">
                <span class="fw-lighter">{{ thisWeekDistances[0].translatedName }}</span>
                <br>
                <p v-if="thisWeekDistances[0].longMeters">
                   <span v-if="thisWeekDistances && thisWeekDistances[0].distance">
                      {{ thisWeekDistances[0].distance> 10000 ? (thisWeekDistances[0].distance / 1000).toFixed(2) + ' km' : thisWeekDistances[0].distance + ' m' }}
                  </span>
                  <span v-else>0 m</span>
                </p>
                <p v-else>
                  <span>{{ thisWeekDistances && thisWeekDistances[0].distance ? (thisWeekDistances[0].distance / 1000).toFixed(2) + ' km' : '0 km' }}</span>
                </p>
            </div>
            <div class="col border-start border-opacity-50 text-center">
                <span class="fw-lighter">{{ thisWeekDistances[1].translatedName }}</span>
                <br>
                <p v-if="thisWeekDistances[1].longMeters">
                     <span v-if="thisWeekDistances && thisWeekDistances[1].distance">
                        {{ thisWeekDistances[1].distance> 10000 ? (thisWeekDistances[1].distance / 1000).toFixed(2) + ' km' : thisWeekDistances[1].distance + ' m' }}
                    </span>
                  <span v-else>0 m</span>
                </p>
                <p v-else>
                  <span>{{ thisWeekDistances && thisWeekDistances[1].distance ? (thisWeekDistances[1].distance / 1000).toFixed(2) + ' km' : '0 km' }}</span>
                </p>
            </div>
            <div class="col border-start border-opacity-50 text-end">
                <span class="fw-lighter">{{ thisWeekDistances[2].translatedName }}</span>
                <br>
                <p v-if="thisWeekDistances[2].longMeters">
                     <span v-if="thisWeekDistances && thisWeekDistances[2].distance">
                        {{ thisWeekDistances[2].distance> 10000 ? (thisWeekDistances[2].distance / 1000).toFixed(2) + ' km' : thisWeekDistances[2].distance + ' m' }}
                    </span>
                  <span v-else>0 m</span>
                </p>
                <p v-else>
                  <span>{{ thisWeekDistances && thisWeekDistances[2].distance ? (thisWeekDistances[2].distance / 1000).toFixed(2) + ' km' : '0 km' }}</span>
                </p>
            </div>
        </div>

        <span class="fw-lighter">{{ $t("userDistanceStats.thisMonthDistancesTitle") }}</span>
        <div class="row mb-3">
            <div class="col text-start">
                <span class="fw-lighter">{{ thisMonthDistances[0].translatedName }}</span>
                <br>
                <p v-if="thisMonthDistances[0].longMeters">
                     <span v-if="thisMonthDistances && thisMonthDistances[0].distance">
                        {{ thisMonthDistances[0].distance> 10000 ? (thisMonthDistances[0].distance / 1000).toFixed(2) + ' km' : thisMonthDistances[0].distance + ' m' }}
                    </span>
                  <span v-else>0 m</span>
                </p>
                <p v-else>
                  <span>{{ thisMonthDistances && thisMonthDistances[0].distance ? (thisMonthDistances[0].distance / 1000).toFixed(2) + ' km' : '0 km' }}</span>
                </p>
            </div>
            <div class="col border-start border-opacity-50 text-center">
                <span class="fw-lighter">{{ thisMonthDistances[1].translatedName }}</span>
                <br>
                <p v-if="thisMonthDistances[1].longMeters">
                       <span v-if="thisMonthDistances && thisMonthDistances[1].distance">
                          {{ thisMonthDistances[1].distance> 10000 ? (thisMonthDistances[1].distance / 1000).toFixed(2) + ' km' : thisMonthDistances[1].distance + ' m' }}
                      </span>
                  <span v-else>0 m</span>
                </p>
                <p v-else>
                  <span>{{ thisMonthDistances && thisMonthDistances[1].distance ? (thisMonthDistances[1].distance / 1000).toFixed(2) + ' km' : '0 km' }}</span>
                </p>
            </div>
            <div class="col border-start border-opacity-50 text-end">
                <span class="fw-lighter">{{ thisMonthDistances[2].translatedName }}</span>
                <br>
                <p v-if="thisMonthDistances[2].longMeters">
                       <span v-if="thisMonthDistances && thisMonthDistances[2].distance">
                          {{ thisMonthDistances[2].distance> 10000 ? (thisMonthDistances[2].distance / 1000).toFixed(2) + ' km' : thisMonthDistances[2].distance + ' m' }}
                      </span>
                  <span v-else>0 m</span>
                </p>
                <p v-else>
                  <span>{{ thisMonthDistances && thisMonthDistances[2].distance ? (thisMonthDistances[2].distance / 1000).toFixed(2) + ' km' : '0 km' }}</span>
                </p>
            </div>
        </div>
    </div>
</template>

<script>
import { computed, watch } from 'vue';
import { useI18n } from 'vue-i18n';

export default {
  props: {
    thisWeekDistances: {
      type: Object,
      required: true,
    },
    thisMonthDistances: {
      type: Object,
      required: true,
    },
  },
  setup(props) {
    const { t } = useI18n();

    const getTopThreeActivities = (distances) => {
      // longMeters if the conversion from meters to km should start at 10000m
      const activities = [
        { name: 'run', translatedName: t("userDistanceStats.distancesRun"),longMeters: false, distance: distances.run },
        { name: 'bike', translatedName: t("userDistanceStats.distancesBike"),longMeters: false, distance: distances.bike },
        { name: 'swim', translatedName: t("userDistanceStats.distancesSwim"),longMeters: true, distance: distances.swim },
        { name: 'walk', translatedName: t("userDistanceStats.distancesWalk"),longMeters: false, distance: distances.walk },
        { name: 'hike', translatedName: t("userDistanceStats.distancesHike"),longMeters: false, distance: distances.hike },
        { name: 'rowing', translatedName: t("userDistanceStats.distancesRowing"),longMeters: false, distance: distances.rowing },
        { name: 'ski', translatedName: t("userDistanceStats.distancesSki"),longMeters: false, distance: distances.ski },
      ];
      const sortedActivities = activities.sort((a, b) => b.distance - a.distance);
      return sortedActivities.slice(0, 3);
    };

    const thisWeek = computed(() => getTopThreeActivities(props.thisWeekDistances));
    const thisMonth = computed(() => getTopThreeActivities(props.thisMonthDistances));

    watch([thisWeek, thisMonth], () => {
      console.log('This Week Top Activities:', thisWeek.value);
      console.log('This Month Top Activities:', thisMonth.value);
    });

    return {
      thisWeekDistances: thisWeek,
      thisMonthDistances: thisMonth,
    };
  },
};
</script>
