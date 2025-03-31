<template>
    <div class="table-responsive d-none d-sm-block">
        <table class="table table-striped table-borderless table-hover table-sm rounded text-center" style="--bs-table-bg: var(--bs-gray-850);">
            <thead>
                <tr>
                    <th>{{ $t("activityLapsComponent.labelLapNumber") }}</th>
                    <th>{{ $t("activityLapsComponent.labelLapDistance") }}</th>
                    <th>{{ $t("activityLapsComponent.labelLapTime") }}</th>
                    <th>{{ $t("activityLapsComponent.labelLapPace") }}</th>
                    <th>{{ $t("activityLapsComponent.labelLapElevation") }}</th>
                    <th>{{ $t("activityLapsComponent.labelLapAvgHr") }}</th>
                </tr>
            </thead>
            <tbody class="table-group-divider">
                <tr v-for="(lap, index) in activityActivityLaps" :key="lap.id">
                    <td>{{ index + 1 }}</td>
                    <td>{{ metersToKm(lap.total_distance) + ' ' + $t("generalItems.unitsKm") }}</td>
                    <td>{{ formatSecondsToMinutes(lap.total_elapsed_time) }}</td>
                    <td>{{ formatPaceMetric(lap.enhanced_avg_pace) }}</td>
                    <td>{{ (lap.total_ascent || 0) + ' ' + $t("generalItems.unitsM") }}</td>
                    <td>{{ lap.avg_heart_rate + ' ' + $t("generalItems.unitsBpm") }}</td>
                </tr>
            </tbody>
        </table>
    </div>

    <div class="table-responsive d-lg-none d-block">
        <table class="table table-sm table-borderless" style="--bs-table-bg: var(--bs-gray-850);">
            <thead>
                <tr>
                    <th scope="col" style="width: 5%;">#</th>
                    <th scope="col" style="width: 15%;">{{ $t("activityLapsComponent.labelLapPace") }}</th>
                    <th scope="col" style="width: auto;">&nbsp;</th>
                    <th scope="col" style="width: 10%;">{{ $t("activityLapsComponent.labelLapElev") }}</th>
                    <th scope="col" style="width: 10%;">{{ $t("activityLapsComponent.labelLapHR") }}</th>
                </tr>
            </thead>
            <tbody>
                <tr v-for="(lap, index) in normalizedLaps" :key="index">
                    <td>{{ index + 1 }}</td>
                    <td>{{ lap.formattedPace }}</td>
                    <td>
                        <div class="progress" role="progressbar" aria-label="Basic example" aria-valuenow="0" aria-valuemin="0" aria-valuemax="100">
                            <div class="progress-bar" :style="{ width: lap.normalizedScore + '%' }"></div>
                        </div>
                    </td>
                    <td>{{ lap.total_ascent ?? 0 }}</td>
                    <td>{{ lap.avg_heart_rate ?? 0 }}</td>
                </tr>
            </tbody>
        </table>
        <hr>
    </div>
</template>

<script>
import { ref, computed } from "vue";
// Importing the components
import LoadingComponent from "@/components/GeneralComponents/LoadingComponent.vue";
import { formatSecondsToMinutes } from "@/utils/dateTimeUtils";
import { formatPaceMetric, formatPaceImperial, formatPaceSwimMetric, formatPaceSwimImperial, formatAverageSpeedMetric, formatAverageSpeedImperial } from "@/utils/activityUtils";
import { metersToKm, metersToMiles, metersToYards, metersToFeet } from "@/utils/unitsUtils";

export default {
	components: {
		LoadingComponent,
	},
	props: {
		activity: {
			type: Object,
			required: true,
		},
		activityActivityLaps: {
			type: Object,
			required: true,
		},
        units: {
            type: Number,
			default: 1,
        },
	},
	setup(props) {

		return {
            formatSecondsToMinutes,
            formatPaceMetric,
            metersToKm,
		};
	},
};
</script>