<template>
    <div class="table-responsive d-none d-sm-block">
        <table class="table table-striped table-borderless table-hover table-sm rounded text-center" style="--bs-table-bg: var(--bs-gray-850);">
            <thead>
                <tr>
                    <th>{{ $t("activityLapsComponent.labelLapNumber") }}</th>
                    <th>{{ $t("activityLapsComponent.labelLapDistance") }}</th>
                    <th>{{ $t("activityLapsComponent.labelLapTime") }}</th>
                    <th v-if="activity.activity_type === 4 || activity.activity_type === 5 || activity.activity_type === 6 || activity.activity_type === 7">{{ $t("activityLapsComponent.labelLapSpeed") }}</th>
                    <th v-else>{{ $t("activityLapsComponent.labelLapPace") }}</th>
                    <th>{{ $t("activityLapsComponent.labelLapElevation") }}</th>
                    <th>{{ $t("activityLapsComponent.labelLapAvgHr") }}</th>
                </tr>
            </thead>
            <tbody class="table-group-divider">
                <tr v-for="(lap, index) in normalizedLaps" :key="lap.id">
                    <td>{{ index + 1 }}</td>
                    <td>{{ lap.formattedDistance }}</td>
                    <td>{{ lap.lapSecondsToMinutes }}</td>
                    <td v-if="activity.activity_type === 4 || activity.activity_type === 5 || activity.activity_type === 6 || activity.activity_type === 7">{{ lap.formattedSpeedFull }}</td>
                    <td v-else>{{ lap.formattedPaceFull }}</td>
					<td>{{ lap.formattedElevationFull.value }}</td>
                    <td>{{ lap.avg_heart_rate ?? 0 + ' ' + $t("generalItems.unitsBpm") }}</td>
                </tr>
            </tbody>
        </table>
    </div>

    <div class="table-responsive d-lg-none d-block">
        <table class="table table-sm table-borderless" style="--bs-table-bg: var(--bs-gray-850);">
            <thead>
                <tr>
                    <th scope="col" style="width: 5%;">#</th>
                    <th scope="col" style="width: 15%;" v-if="activity.activity_type === 4 || activity.activity_type === 5 || activity.activity_type === 6 || activity.activity_type === 7">{{ $t("activityLapsComponent.labelLapSpeed") }}</th>
                    <th scope="col" style="width: 15%;" v-else>{{ $t("activityLapsComponent.labelLapPace") }}</th>
                    <th scope="col" style="width: auto;">&nbsp;</th>
                    <th scope="col" style="width: 10%;">{{ $t("activityLapsComponent.labelLapElev") }}</th>
                    <th scope="col" style="width: 10%;">{{ $t("activityLapsComponent.labelLapHR") }}</th>
                </tr>
            </thead>
            <tbody>
                <tr v-for="(lap, index) in normalizedLaps" :key="index">
                    <td>{{ index + 1 }}</td>
                    <td v-if="activity.activity_type === 4 || activity.activity_type === 5 || activity.activity_type === 6 || activity.activity_type === 7">{{ lap.formattedSpeed }}</td>
                    <td v-else>{{ lap.formattedPace }}</td>
                    <td>
                        <div class="progress" role="progressbar" aria-label="Basic example" aria-valuenow="0" aria-valuemin="0" aria-valuemax="100">
                            <div class="progress-bar" :style="{ width: lap.normalizedScore + '%' }"></div>
                        </div>
                    </td>
                    <td>{{ lap.formattedElevation }}</td>
                    <td>{{ lap.avg_heart_rate ?? 0 }}</td>
                </tr>
            </tbody>
        </table>
        <hr>
    </div>
</template>

<script>
import { ref, computed } from "vue";
import { useI18n } from "vue-i18n";
// Importing the components
import LoadingComponent from "@/components/GeneralComponents/LoadingComponent.vue";
import { formatSecondsToMinutes } from "@/utils/dateTimeUtils";
import {
	formatPaceMetric,
	formatPaceImperial,
	formatPaceSwimMetric,
	formatPaceSwimImperial,
	formatAverageSpeedMetric,
	formatAverageSpeedImperial,
} from "@/utils/activityUtils";
import {
	metersToKm,
	metersToMiles,
	metersToYards,
	metersToFeet,
} from "@/utils/unitsUtils";

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
			type: [Object, null],
			required: true,
		},
		units: {
			type: Number,
			required: true,
		},
	},
	setup(props) {
		const { t } = useI18n();
		const normalizedLaps = computed(() => {
			if (
				!props.activityActivityLaps ||
				props.activityActivityLaps.length === 0
			) {
				return [];
			}

			// Extract all enhanced_avg_pace values
			const laps = props.activityActivityLaps;
			const enhancedAvgPaces = laps.map((lap) => lap.enhanced_avg_pace);

			// Find the fastest pace (smallest value)
			const fastestPace = Math.min(...enhancedAvgPaces);

			// Normalize each lap's pace relative to the fastest
			return laps.map((lap) => {
				const normalizedScore = (fastestPace / lap.enhanced_avg_pace) * 100;
				const formattedPace = computed(() => {
					if (
						props.activity.activity_type === 8 ||
						props.activity.activity_type === 9 ||
						props.activity.activity_type === 13
					) {
						if (Number(props.units) === 1) {
							return formatPaceSwimMetric(lap.enhanced_avg_pace, false);
						}
						return formatPaceSwimImperial(lap.enhanced_avg_pace, false);
					}
					if (Number(props.units) === 1) {
						return formatPaceMetric(lap.enhanced_avg_pace, false);
					}
					return formatPaceImperial(lap.enhanced_avg_pace, false);
				});
				const formattedPaceFull = computed(() => {
					if (
						props.activity.activity_type === 8 ||
						props.activity.activity_type === 9 ||
						props.activity.activity_type === 13
					) {
						if (Number(props.units) === 1) {
							return formatPaceSwimMetric(lap.enhanced_avg_pace);
						}
						return formatPaceSwimImperial(lap.enhanced_avg_pace);
					}
					if (Number(props.units) === 1) {
						return formatPaceMetric(lap.enhanced_avg_pace);
					}
					return formatPaceImperial(lap.enhanced_avg_pace);
				});
				const formattedDistance = computed(() => {
					if (Number(props.units) === 1) {
						return `${metersToKm(lap.total_distance)} ${t("generalItems.unitsKm")}`;
					}
					return `${metersToMiles(lap.total_distance)} ${t("generalItems.unitsMiles")}`;
				});
                const formattedElevation = computed(() => {
                    if (Number(props.units) === 1) {
                        return lap.total_ascent ?? 0;
                    }
                    return metersToFeet(lap.total_ascent) ?? 0;
                });
                const formattedElevationFull = computed(() => {
                    if (Number(props.units) === 1) {
                        return `${lap.total_ascent} ${t("generalItems.unitsM")}` ?? `0 ${t("generalItems.unitsM")}`;
                    }
                    return `${metersToFeet(lap.total_ascent)} ${t("generalItems.unitsFeetShort")}` ?? `0 ${t("generalItems.unitsFeetShort")}`;
                });
                const formattedSpeedFull = computed(() => {
                    if (Number(props.units) === 1) {
                        return `${lap.enhanced_avg_speed} ${t("generalItems.unitsKmH")}`;
                    }
                    return `${formatAverageSpeedImperial(lap.enhanced_avg_speed)} ${t("generalItems.unitsMph")}`;
                });
                const formattedSpeed = computed(() => {
                    if (Number(props.units) === 1) {
                        return lap.enhanced_avg_speed ?? 0;
                    }
                    return formatAverageSpeedImperial(lap.enhanced_avg_speed) ?? 0;
                });

				return {
					...lap,
					normalizedScore: Math.min(Math.max(normalizedScore, 0), 100), // Clamp between 0 and 100
					formattedPace: formattedPace,
					formattedPaceFull: formattedPaceFull,
					lapSecondsToMinutes: formatSecondsToMinutes(lap.total_elapsed_time),
                    formattedDistance: formattedDistance,
                    formattedElevation: formattedElevation,
                    formattedElevationFull: formattedElevationFull,
                    formattedSpeedFull: formattedSpeedFull,
                    formattedSpeed: formattedSpeed,
				};
			});
		});

		return {
			normalizedLaps,
		};
	},
};
</script>