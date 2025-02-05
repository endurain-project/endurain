<template>
    <div class="mb-3 mt-3">
        <span class="fw-lighter">{{ $t("userDistanceStats.thisWeekDistancesTitle") }}</span>
        <div class="row mb-3">
            <!-- this week col one -->
            <div class="col text-start">
				<span class="fw-lighter">{{ thisWeek[0].translatedName }}</span>
				<br>
				<span v-if="Number(authStore?.user?.units) === 1">
					{{ thisWeek && thisWeek[0].distance ? thisWeek[0].distance + ' ' : '0 ' }}
					<span v-if="thisWeek[0].useMeters">
						{{ $t("generalItems.unitsM") }}
					</span>
					<span v-else>
						{{ $t("generalItems.unitsKm") }}
					</span>
				</span>
				<span v-else>
					{{ thisWeek && thisWeek[0].distance ? thisWeek[0].distance + ' ' : '0 ' }}
					<span v-if="thisWeek[0].useMeters">
						{{ $t("generalItems.unitsYards") }}
					</span>
					<span v-else>
						{{ $t("generalItems.unitsMiles") }}
					</span>
				</span>
            </div>
            <!-- this week col two -->
            <div class="col border-start border-opacity-50 text-center">
              <span class="fw-lighter">{{ thisWeek[1].translatedName }}</span>
              <br>
              <span v-if="Number(authStore?.user?.units) === 1">
                {{ thisWeek && thisWeek[1].distance ? thisWeek[1].distance + ' ' : '0 ' }}
                <span v-if="thisWeek[1].useMeters">
                  {{ $t("generalItems.unitsM") }}
                </span>
                <span v-else>
                  {{ $t("generalItems.unitsKm") }}
                </span>
              </span>
              <span v-else>
                {{ thisWeek && thisWeek[1].distance ? thisWeek[1].distance + ' ' : '0 ' }}
                <span v-if="thisWeek[1].useMeters">
                  {{ $t("generalItems.unitsYards") }}
                </span>
                <span v-else>
                  {{ $t("generalItems.unitsMiles") }}
                </span>
              </span>
            </div>
            <!-- this week col three -->
            <div class="col border-start border-opacity-50 text-end">
              <span class="fw-lighter">{{ thisWeek[2].translatedName }}</span>
              <br>
              <span v-if="Number(authStore?.user?.units) === 1">
                {{ thisWeek && thisWeek[2].distance ? thisWeek[2].distance + ' ' : '0 ' }}
                <span v-if="thisWeek[2].useMeters">
                  {{ $t("generalItems.unitsM") }}
                </span>
                <span v-else>
                  {{ $t("generalItems.unitsKm") }}
                </span>
              </span>
              <span v-else>
                {{ thisWeek && thisWeek[2].distance ? thisWeek[2].distance + ' ' : '0 ' }}
                <span v-if="thisWeek[2].useMeters">
                  {{ $t("generalItems.unitsYards") }}
                </span>
                <span v-else>
                  {{ $t("generalItems.unitsMiles") }}
                </span>
              </span>
            </div>
        </div>
        
        <span class="fw-lighter">{{ $t("userDistanceStats.thisMonthDistancesTitle") }}</span>
        <div class="row mb-3">
            <!-- this week col one -->
            <div class="col text-start">
				<span class="fw-lighter">{{ thisMonth[0].translatedName }}</span>
				<br>
				<span v-if="Number(authStore?.user?.units) === 1">
					{{ thisMonth && thisMonth[0].distance ? thisMonth[0].distance + ' ' : '0 ' }}
					<span v-if="thisMonth[0].useMeters">
						{{ $t("generalItems.unitsM") }}
					</span>
					<span v-else>
						{{ $t("generalItems.unitsKm") }}
					</span>
				</span>
				<span v-else>
					{{ thisMonth && thisMonth[0].distance ? thisMonth[0].distance + ' ' : '0 ' }}
					<span v-if="thisMonth[0].useMeters">
						{{ $t("generalItems.unitsYards") }}
					</span>
					<span v-else>
						{{ $t("generalItems.unitsMiles") }}
					</span>
				</span>
            </div>
            <!-- this week col two -->
            <div class="col border-start border-opacity-50 text-center">
              <span class="fw-lighter">{{ thisMonth[1].translatedName }}</span>
              <br>
              <span v-if="Number(authStore?.user?.units) === 1">
                {{ thisMonth && thisMonth[1].distance ? thisMonth[1].distance + ' ' : '0 ' }}
                <span v-if="thisMonth[1].useMeters">
                  {{ $t("generalItems.unitsM") }}
                </span>
                <span v-else>
                  {{ $t("generalItems.unitsKm") }}
                </span>
              </span>
              <span v-else>
                {{ thisMonth && thisMonth[1].distance ? thisMonth[1].distance + ' ' : '0 ' }}
                <span v-if="thisMonth[1].useMeters">
                  {{ $t("generalItems.unitsYards") }}
                </span>
                <span v-else>
                  {{ $t("generalItems.unitsMiles") }}
                </span>
              </span>
            </div>
            <!-- this week col three -->
            <div class="col border-start border-opacity-50 text-end">
              <span class="fw-lighter">{{ thisMonth[2].translatedName }}</span>
              <br>
              <span v-if="Number(authStore?.user?.units) === 1">
                {{ thisMonth && thisMonth[2].distance ? thisMonth[2].distance + ' ' : '0 ' }}
                <span v-if="thisMonth[2].useMeters">
                  {{ $t("generalItems.unitsM") }}
                </span>
                <span v-else>
                  {{ $t("generalItems.unitsKm") }}
                </span>
              </span>
              <span v-else>
                {{ thisMonth && thisMonth[2].distance ? thisMonth[2].distance + ' ' : '0 ' }}
                <span v-if="thisMonth[2].useMeters">
                  {{ $t("generalItems.unitsYards") }}
                </span>
                <span v-else>
                  {{ $t("generalItems.unitsMiles") }}
                </span>
              </span>
            </div>
        </div>
    </div>
</template>

<script>
// Importing the stores
import { computed } from "vue";
import { useI18n } from 'vue-i18n';
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
        const { t } = useI18n();
		const getTopThreeActivities = (distances) => {
			const convertDistanceMetersToKmsOrMiles = (distance) => 
				Number(authStore.user.units) === 1 ? metersToKm(distance) : metersToMiles(distance);
			const convertDistanceMetersToYards = (distance) => 
				Number(authStore.user.units) === 1 ? distance : metersToYards(distance);

			const activities = [
				{
					name: "run",
					translatedName: t("userDistanceStats.distancesRun"),
					useMeters: false,
					distance: convertDistanceMetersToKmsOrMiles(distances.run),
				},
				{
					name: "bike",
					translatedName: t("userDistanceStats.distancesBike"),
					useMeters: false,
					distance: convertDistanceMetersToKmsOrMiles(distances.bike),
				},
				{
					name: "swim",
					translatedName: t("userDistanceStats.distancesSwim"),
					useMeters: true,
					distance: convertDistanceMetersToYards(distances.swim),
				},
				{
					name: "walk",
					translatedName: t("userDistanceStats.distancesWalk"),
					useMeters: false,
					distance: convertDistanceMetersToKmsOrMiles(distances.walk),
				},
				{
					name: "hike",
					translatedName: t("userDistanceStats.distancesHike"),
					useMeters: false,
					distance: convertDistanceMetersToKmsOrMiles(distances.hike),
				},
				{
					name: "rowing",
					translatedName: t("userDistanceStats.distancesRowing"),
					useMeters: false,
					distance: convertDistanceMetersToKmsOrMiles(distances.rowing),
				},
				{
					name: "snow_ski",
					translatedName: t("userDistanceStats.distancesSnowSki"),
					useMeters: false,
					distance: convertDistanceMetersToKmsOrMiles(distances.ski),
				},
				{
					name: "snowboard",
					translatedName: t("userDistanceStats.distancesSnowboard"),
					useMeters: false,
					distance: convertDistanceMetersToKmsOrMiles(distances.snowboard),
				},
			];
			// Sort activities by distance
			const sortedActivities = activities.sort(
				(a, b) => b.distance - a.distance,
			);
			// Return top 3 activities
			return sortedActivities.slice(0, 3);
		};
		const thisWeek = computed(() =>
			getTopThreeActivities(props.thisWeekDistances),
		);
		const thisMonth = computed(() =>
			getTopThreeActivities(props.thisMonthDistances),
		);

		return {
			authStore,
			metersToKm,
			metersToMiles,
			metersToYards,
			thisWeek,
			thisMonth,
		};
	},
};
</script>