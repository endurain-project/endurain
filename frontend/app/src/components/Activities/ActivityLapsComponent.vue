<template>
    <div class="table-responsive">
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
		activityActivityLaps: {
			type: Object,
			required: true,
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