<template>
    <div class="mb-3 mt-3">
        <span class="fw-lighter">{{ $t("userDistanceStats.thisWeekDistancesTitle") }}</span>
        <div class="row mb-3">
            <div class="col text-start">
                <span class="fw-lighter">{{ $t("userDistanceStats.distancesRun") }}</span>
                <br>
                <span v-if="Number(authStore?.user?.units) === 1">{{ thisWeekDistances && thisWeekDistances.run ? metersToKm(thisWeekDistances.run) + ' ' + $t("generalItems.unitsKm") : '0 ' + $t("generalItems.unitsKm") }}</span>
                <span v-else>{{ thisWeekDistances && thisWeekDistances.run ? metersToMiles(thisWeekDistances.run) + ' ' + $t("generalItems.unitsMiles") : '0 ' + $t("generalItems.unitsMiles") }}</span>
            </div>
            <div class="col border-start border-opacity-50 text-center">
                <span class="fw-lighter">{{ $t("userDistanceStats.distancesBike") }}</span>
                <br>
                <span v-if="Number(authStore?.user?.units) === 1">{{ thisWeekDistances && thisWeekDistances.bike ? metersToKm(thisWeekDistances.bike) + ' ' + $t("generalItems.unitsKm") : '0 ' + $t("generalItems.unitsKm") }}</span>
                <span v-else>{{ thisWeekDistances && thisWeekDistances.bike ? metersToMiles(thisWeekDistances.bike) + ' ' + $t("generalItems.unitsMiles") : '0 ' + $t("generalItems.unitsMiles") }}</span>
            </div>
            <div class="col border-start border-opacity-50 text-end">
                <span class="fw-lighter">{{ $t("userDistanceStats.distancesSwim") }}</span>
                <br>
                <span v-if="thisWeekDistances && thisWeekDistances.swim">
                    <span v-if="Number(authStore?.user?.units) === 1">{{ thisWeekDistances.swim > 10000 ? metersToKm(thisWeekDistances.swim) + ' ' + $t("generalItems.unitsKm") : thisWeekDistances.swim + ' ' + $t("generalItems.unitsM") }}</span>
                    <span v-else>{{ metersToYards(thisWeekDistances.swim) + ' ' + $t("generalItems.unitsYards") }}</span>
                </span>
                <span v-else>
                    <span v-if="Number(authStore?.user?.units) === 1">0 {{ $t("generalItems.unitsM") }}</span>
                    <span v-else>0 {{ $t("generalItems.unitsYards") }}</span>
                </span>
            </div>
        </div>
        
        <span class="fw-lighter">{{ $t("userDistanceStats.thisMonthDistancesTitle") }}</span>
        <div class="row mb-3">
            <div class="col text-start">
                <span class="fw-lighter">{{ $t("userDistanceStats.distancesRun") }}</span>
                <br>
                <span v-if="Number(authStore?.user?.units) === 1">{{ thisMonthDistances && thisMonthDistances.run ? metersToKm(thisMonthDistances.run) + ' ' + $t("generalItems.unitsKm") : '0 ' + $t("generalItems.unitsKm") }}</span>
                <span v-else>{{ thisMonthDistances && thisMonthDistances.run ? metersToMiles(thisMonthDistances.run) + ' ' + $t("generalItems.unitsMiles") : '0 ' + $t("generalItems.unitsMiles") }}</span>
            </div>
            <div class="col border-start border-opacity-50 text-center">
                <span class="fw-lighter">{{ $t("userDistanceStats.distancesBike") }}</span>
                <br>
                <span v-if="Number(authStore?.user?.units) === 1">{{ thisMonthDistances && thisMonthDistances.bike ? metersToKm(thisMonthDistances.bike) + ' ' + $t("generalItems.unitsKm") : '0 ' + $t("generalItems.unitsKm") }}</span>
                <span v-else>{{ thisMonthDistances && thisMonthDistances.bike ? metersToMiles(thisMonthDistances.bike) + ' ' + $t("generalItems.unitsMiles") : '0 ' + $t("generalItems.unitsMiles") }}</span>
            </div>
            <div class="col border-start border-opacity-50 text-end">
                <span class="fw-lighter">{{ $t("userDistanceStats.distancesSwim") }}</span>
                <br>
                <span v-if="thisMonthDistances && thisMonthDistances.swim">
                    <span v-if="Number(authStore?.user?.units) === 1">{{ thisMonthDistances.swim > 10000 ? metersToKm(thisMonthDistances.swim) + ' ' + $t("generalItems.unitsKm") : thisMonthDistances.swim + ' ' + $t("generalItems.unitsM") }}</span>
                    <span v-else>{{ metersToYards(thisMonthDistances.swim) + ' ' + $t("generalItems.unitsYards") }}</span>
                </span>
                <span v-else>
                    <span v-if="Number(authStore?.user?.units) === 1">0 {{ $t("generalItems.unitsM") }}</span>
                    <span v-else>0 {{ $t("generalItems.unitsYards") }}</span>
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