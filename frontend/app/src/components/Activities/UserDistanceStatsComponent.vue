<template>
    <div class="mb-3 mt-3">
        <span class="fw-lighter">{{ $t("userDistanceStats.thisWeekDistancesTitle") }}</span>
        <div class="row mb-3">
            <div class="col">
                <span class="fw-lighter">{{ $t("userDistanceStats.distancesRun") }}</span>
                <br>
                <span>{{ thisWeekDistances && thisWeekDistances.run ? (thisWeekDistances.run / 1000).toFixed(2) + ' km' : '0 km' }}</span>
            </div>
            <div class="col border-start border-opacity-50">
                <span class="fw-lighter">{{ $t("userDistanceStats.distancesBike") }}</span>
                <br>
                <span>{{ thisWeekDistances && thisWeekDistances.bike ? (thisWeekDistances.bike / 1000).toFixed(2) + ' km' : '0 km' }}</span>
            </div>
            <div class="col border-start border-opacity-50">
                <span class="fw-lighter">{{ $t("userDistanceStats.distancesSwim") }}</span>
                <br>
                <span v-if="thisWeekDistances && thisWeekDistances.swim">
                    {{ thisWeekDistances.swim > 10000 ? (thisWeekDistances.swim / 1000).toFixed(2) + ' km' : thisWeekDistances.swim + ' m' }}
                </span>
                <span v-else>0 m</span>
            </div>
        </div>
    </div>
    <div>
        <span class="fw-lighter">{{ $t("userDistanceStats.thisMonthDistancesTitle") }}</span>
        <div class="row mb-3">
            <div class="col">
                <span class="fw-lighter">{{ $t("userDistanceStats.distancesRun") }}</span>
                <br>
                <span>{{ thisMonthDistances && thisMonthDistances.run ? (thisMonthDistances.run / 1000).toFixed(2) + ' km' : '0 km' }}</span>
            </div>
            <div class="col border-start border-opacity-50">
                <span class="fw-lighter">{{ $t("userDistanceStats.distancesBike") }}</span>
                <br>
                <span>{{ thisMonthDistances && thisMonthDistances.bike ? (thisMonthDistances.bike / 1000).toFixed(2) + ' km' : '0 km' }}</span>
            </div>
            <div class="col border-start border-opacity-50">
                <span class="fw-lighter">{{ $t("userDistanceStats.distancesSwim") }}</span>
                <br>
                <span v-if="thisMonthDistances && thisMonthDistances.swim">
                    {{ thisMonthDistances.swim > 10000 ? (thisMonthDistances.swim / 1000).toFixed(2) + ' km' : thisMonthDistances.swim + ' m' }}
                </span>
                <span v-else>0 m</span>
            </div>
        </div>
    </div>
</template>

<script>
import { computed } from 'vue';
import { useUserStore } from '@/stores/userStore';

export default {
  setup() {
    const userStore = useUserStore();

    // Access both stats directly from the store
    const thisWeekDistances = computed(() => userStore.thisWeekDistances);
    const thisMonthDistances = computed(() => userStore.thisMonthDistances);

    return {
      thisWeekDistances,
      thisMonthDistances,
    };
  },
};
</script>