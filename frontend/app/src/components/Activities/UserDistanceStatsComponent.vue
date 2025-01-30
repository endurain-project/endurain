<template>
    <div class="mb-3 mt-3">
        <span class="fw-lighter">{{ $t("userDistanceStats.thisWeekDistancesTitle") }}</span>
        <div class="row mb-3">
            <div class="col text-start">
                <span class="fw-lighter">{{ $t("userDistanceStats.distancesRun") }}</span>
                <br>
                <span v-if="authStore.user.units == 1">{{ thisWeekDistances && thisWeekDistances.run ? metersToKm(thisWeekDistances.run) + ' km' : '0 km' }}</span>
                <span v-else>{{ thisWeekDistances && thisWeekDistances.run ? metersToMiles(thisWeekDistances.run) + ' mi' : '0 mi' }}</span>
            </div>
            <div class="col border-start border-opacity-50 text-center">
                <span class="fw-lighter">{{ $t("userDistanceStats.distancesBike") }}</span>
                <br>
                <span v-if="authStore.user.units == 1">{{ thisWeekDistances && thisWeekDistances.bike ? metersToKm(thisWeekDistances.bike) + ' km' : '0 km' }}</span>
                <span v-else>{{ thisWeekDistances && thisWeekDistances.bike ? metersToMiles(thisWeekDistances.bike) + ' mi' : '0 mi' }}</span>
            </div>
            <div class="col border-start border-opacity-50 text-end">
                <span class="fw-lighter">{{ $t("userDistanceStats.distancesSwim") }}</span>
                <br>
                <span v-if="thisWeekDistances && thisWeekDistances.swim">
                    <span v-if="authStore.user.units == 1">{{ thisWeekDistances.swim > 10000 ? metersToKm(thisWeekDistances.swim) + ' km' : thisWeekDistances.swim + ' m' }}</span>
                    <span v-else>{{ metersToYards(thisWeekDistances.swim) + ' yd' }}</span>
                </span>
                <span v-else>
                    <span v-if="authStore.user.units == 1">0 m</span>
                    <span v-else>0 yd</span>
                </span>
            </div>
        </div>
        
        <span class="fw-lighter">{{ $t("userDistanceStats.thisMonthDistancesTitle") }}</span>
        <div class="row mb-3">
            <div class="col text-start">
                <span class="fw-lighter">{{ $t("userDistanceStats.distancesRun") }}</span>
                <br>
                <span v-if="authStore.user.units == 1">{{ thisMonthDistances && thisMonthDistances.run ? metersToKm(thisMonthDistances.run) + ' km' : '0 km' }}</span>
                <span v-else>{{ thisMonthDistances && thisMonthDistances.run ? metersToMiles(thisMonthDistances.run) + ' mi' : '0 mi' }}</span>
            </div>
            <div class="col border-start border-opacity-50 text-center">
                <span class="fw-lighter">{{ $t("userDistanceStats.distancesBike") }}</span>
                <br>
                <span v-if="authStore.user.units == 1">{{ thisMonthDistances && thisMonthDistances.bike ? metersToKm(thisMonthDistances.bike) + ' km' : '0 km' }}</span>
                <span v-else>{{ thisMonthDistances && thisMonthDistances.bike ? metersToMiles(thisMonthDistances.bike) + ' mi' : '0 mi' }}</span>
            </div>
            <div class="col border-start border-opacity-50 text-end">
                <span class="fw-lighter">{{ $t("userDistanceStats.distancesSwim") }}</span>
                <br>
                <span v-if="thisMonthDistances && thisMonthDistances.swim">
                    <span v-if="authStore.user.units == 1">{{ thisMonthDistances.swim > 10000 ? metersToKm(thisMonthDistances.swim) + ' km' : thisMonthDistances.swim + ' m' }}</span>
                    <span v-else>{{ metersToYards(thisMonthDistances.swim) + ' yd' }}</span>
                </span>
                <span v-else>
                    <span v-if="authStore.user.units == 1">0 m</span>
                    <span v-else>0 yd</span>
                </span>
            </div>
        </div>
    </div>
</template>

<script>
// Importing the stores
import { useAuthStore } from "@/stores/authStore";
import { metersToKm, metersToMiles, metersToYards } from "@/utils/unitsUtils";

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
        const authStore = useAuthStore(); 

        return {
            authStore,
            metersToKm,
            metersToMiles,
            metersToYards,
        };
    },
};
</script>