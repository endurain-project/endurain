<template>
    <div class="table-responsive d-none d-sm-block">
        {{ activityActivityWorkoutSteps }}
        <table class="table table-striped table-borderless table-hover table-sm rounded text-center" style="--bs-table-bg: var(--bs-gray-850);">
            <thead>
                <tr>
                    <th>#</th>
                    <th>{{ $t("activityWorkoutStepsComponent.labelWorkoutStepType") }}</th>
                    <th>{{ $t("activityWorkoutStepsComponent.labelWorkoutStepTime") }}</th>
                    <th>Repetitions</th>
                    <th>{{ $t("activityWorkoutStepsComponent.labelWorkoutStepTarget") }}</th>
                    <th>{{ $t("activityWorkoutStepsComponent.labelWorkoutStepIntensity") }}</th>
                    <th v-if="activity.activity_type === 10 || activity.activity_type === 19 || activity.activity_type === 20">{{ $t("activityWorkoutStepsComponent.labelWorkoutStepExerciseName") }}</th>
                    <th v-if="activity.activity_type === 10 || activity.activity_type === 19 || activity.activity_type === 20">{{ $t("activityWorkoutStepsComponent.labelWorkoutStepExerciseWeight") }}</th>
                    <th>{{ $t("activityWorkoutStepsComponent.labelWorkoutStepNotes") }}</th>
                </tr>
            </thead>
            <tbody class="table-group-divider">
                <tr v-for="(step, index) in processedWorkoutSteps" :key="step.id">
                    <td>{{ index + 1 }}</td>
                    <td>{{ step.duration_type ?? $t("generalItems.labelNoData") }}</td>
                    <td>
                        <span v-if="step.duration_type === 'time'">
                            {{ formatSecondsToMinutes(step.duration_value) }}
                        </span>
                    </td>
                    <td>
                        <span v-if="step.duration_type === 'reps'">
                            {{ step.duration_value }}
                        </span>
                    </td>
                    <td>{{ step.target_type ?? $t("generalItems.labelNoData") }}</td>
                    <td>{{ step.intensity ?? $t("generalItems.labelNoData") }}</td>
                    <td v-if="activity.activity_type === 10 || activity.activity_type === 19 || activity.activity_type === 20">
                        <span v-if="activityActivityExerciseTitles && activityActivityExerciseTitles.some(title => title.exercise_name === step.exercise_name)">
                            {{ activityActivityExerciseTitles.find(title => title.exercise_name === step.exercise_name).wkt_step_name }}
                        </span>
                        <span v-else-if="step.intensity !== 'rest'">
                            {{ step.exercise_name ?? $t("generalItems.labelNoData") }}
                        </span>
                    </td>
                    <td v-if="activity.activity_type === 10 || activity.activity_type === 19 || activity.activity_type === 20">
                        <span v-if="step.intensity !== 'rest'">
                            {{ step.exercise_weight ?? $t("generalItems.labelNoData") }}
                        </span>
                    </td>
                    <td>{{ step.notes ?? $t("generalItems.labelNoData") }}</td>
                </tr>
            </tbody>
        </table>

        {{ activityActivitySets }}

        <table class="table table-striped table-borderless table-hover table-sm rounded text-center" style="--bs-table-bg: var(--bs-gray-850);">
            <thead>
                <tr>
                    <th>#</th>
                    <th>{{ $t("activityWorkoutStepsComponent.labelWorkoutStepType") }}</th>
                    <th>{{ $t("activityWorkoutStepsComponent.labelWorkoutStepTime") }}</th>
                    <th>Repetitions</th>
                    <th v-if="activity.activity_type === 10 || activity.activity_type === 19 || activity.activity_type === 20">{{ $t("activityWorkoutStepsComponent.labelWorkoutStepExerciseName") }}</th>
                    <th v-if="activity.activity_type === 10 || activity.activity_type === 19 || activity.activity_type === 20">{{ $t("activityWorkoutStepsComponent.labelWorkoutStepExerciseWeight") }}</th>
                </tr>
            </thead>
            <tbody class="table-group-divider">
                <tr v-for="(set, index) in activityActivitySets" :key="set.id">
                    <td>{{ index + 1 }}</td>
                    <td>{{ set.set_type ?? $t("generalItems.labelNoData") }}</td>
                    <td>{{ formatSecondsToMinutes(set.duration) }}</td>
                    <td>
                        <span v-if="set.set_type !== 'rest'">
                            {{ set.repetitions ?? $t("generalItems.labelNoData") }}
                        </span>
                    </td>
                    <td v-if="activity.activity_type === 10 || activity.activity_type === 19 || activity.activity_type === 20">
                        <span v-if="activityActivityExerciseTitles && activityActivityExerciseTitles.some(title => title.exercise_name === set.category_subtype) && set.set_type !== 'rest'">
                            {{ activityActivityExerciseTitles.find(title => title.exercise_name === set.category_subtype).wkt_step_name }}
                        </span>
                        <span v-else-if="set.set_type !== 'rest'">
                            {{ set.category_subtype ?? $t("generalItems.labelNoData") }}
                        </span>
                    </td>
                    <td v-if="activity.activity_type === 10 || activity.activity_type === 19 || activity.activity_type === 20">
                        <span v-if="set.set_type !== 'rest'">
                            {{ set.weight ?? $t("generalItems.labelNoData") }}
                        </span>
                    </td>
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
		activity: {
			type: Object,
			required: true,
		},
		activityActivityWorkoutSteps: {
			type: Object,
			required: true,
		},
        units: {
            type: Number,
			default: 1,
        },
		activityActivityExerciseTitles: {
			type: [Object, null],
			required: true,
		},
        activityActivitySets: {
            type: [Object, null],
            required: true,
        },
	},
	setup(props) {
        const processedWorkoutSteps = props.activityActivityWorkoutSteps.reduce((result, step, index, array) => {
            if (step.duration_type === "repeat_until_steps_cmplt") {
                const repeatCount = step.target_value;
                const stepsToRepeat = array.slice(index - 2, index); // Get the two previous steps
                for (let i = 1; i < repeatCount; i++) {
                    result.push(...stepsToRepeat); // Add the repeated steps
                }
            } else {
                result.push(step); // Add the current step if not "repeat_until_steps_cmplt"
            }
            return result;
        }, []);

		return {
            formatSecondsToMinutes,
            formatPaceMetric,
            metersToKm,
            processedWorkoutSteps,
		};
	},
};
</script>