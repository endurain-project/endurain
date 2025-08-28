<template>
	<li class="list-group-item bg-body-tertiary rounded px-0">
		<div class="d-flex justify-content-between">
			<div class="d-flex align-items-center">
				<font-awesome-icon :icon="getIcon(goal.activity_type)" size="2x" />
				<div class="ms-3">
					<div class="fw-bold">
						<span v-if="goal.activity_type == 1">{{ $t("goalsAddEditGoalModalComponent.activityTypeRun")
							}}</span>
						<span v-if="goal.activity_type == 2">{{ $t("goalsAddEditGoalModalComponent.activityTypeBike")
							}}</span>
						<span v-if="goal.activity_type == 3">{{ $t("goalsAddEditGoalModalComponent.activityTypeSwim")
							}}</span>
						<span v-if="goal.activity_type == 4">{{ $t("goalsAddEditGoalModalComponent.activityTypeWalk")
							}}</span>
						<span v-if="goal.activity_type == 5">{{
							$t("goalsAddEditGoalModalComponent.activityTypeStrength") }}</span>
					</div>
					<span v-if="goal.interval == 'daily'">{{ $t("goalsAddEditGoalModalComponent.intervalOption1")
						}}</span>
					<span v-if="goal.interval == 'weekly'">{{ $t("goalsAddEditGoalModalComponent.intervalOption2")
						}}</span>
					<span v-if="goal.interval == 'monthly'">{{ $t("goalsAddEditGoalModalComponent.intervalOption3")
						}}</span>
					<span v-if="goal.interval == 'yearly'">{{ $t("goalsAddEditGoalModalComponent.intervalOption4")
						}}</span>
					<span> | </span>
					<span v-if="goal.goal_type == 1">{{
						$t("goalsAddEditGoalModalComponent.addEditGoalModalCaloriesLabel") }} - {{ goal.goal_calories }}
						{{ $t("generalItems.unitsCalories") }}</span>
					<span v-if="goal.goal_type == 2">{{
						$t("goalsAddEditGoalModalComponent.addEditGoalModalActivitiesNumberLabel") }} - {{
							goal.goal_activities_number }}</span>
					<span v-if="goal.goal_type == 3">{{
						$t("goalsAddEditGoalModalComponent.addEditGoalModalDistanceLabel") }} - {{ goal.goal_distance
						}}</span>
					<span v-if="goal.goal_type == 4">{{
						$t("goalsAddEditGoalModalComponent.addEditGoalModalElevationLabel") }} - {{ goal.goal_elevation
						}}</span>
					<span v-if="goal.goal_type == 5">{{
						$t("goalsAddEditGoalModalComponent.addEditGoalModalDurationLabel") }} - {{ goal.goal_duration
						}}</span>
					<span v-if="goal.goal_type == 6">{{ $t("goalsAddEditGoalModalComponent.addEditGoalModalStepsLabel")
						}} - {{ goal.goal_steps }}</span>
				</div>
			</div>
			<div>
				<!-- edit goal button -->
				<a class="btn btn-link btn-lg link-body-emphasis" href="#" role="button" data-bs-toggle="modal"
					:data-bs-target="`#editGoalModal${goal.id}`"><font-awesome-icon
						:icon="['fas', 'fa-pen-to-square']" /></a>

				<!-- delete goal button -->
				<a class="btn btn-link btn-lg link-body-emphasis" href="#" role="button" data-bs-toggle="modal"
					:data-bs-target="`#deleteGoalModal${goal.id}`"><font-awesome-icon
						:icon="['fas', 'fa-trash-can']" /></a>

				<!-- delete goal modal -->
				<ModalComponent :modalId="`deleteGoalModal${goal.id}`"
					:title="t('goalsListComponent.modalDeleteGoalTitle')"
					:body="`${t('goalsListComponent.modalDeleteGoalBody')}<b>${goal.id}</b>?`"
					:actionButtonType="`danger`" :actionButtonText="t('goalsListComponent.modalDeleteGoalTitle')"
					@submitAction="submitDeleteGoal" />
			</div>
		</div>
	</li>
</template>

<script setup>
import { ref } from "vue";
import { useI18n } from "vue-i18n";

import ModalComponent from "@/components/Modals/ModalComponent.vue";

import { getIcon, activityTypeName } from "@/utils/activityUtils";

import { userGoals as userGoalService } from '@/services/userGoalsService';

const props = defineProps({
	goal: {
		type: Object,
		required: true,
	},
});

const emit = defineEmits(["goalDeleted", "editedGoal"]);

const { t } = useI18n();

async function submitDeleteGoal() {
	try {
		await userGoalService.deleteGoal(goal.id);
		emit("goalDeleted", goal.id);
	} catch (error) {
		push.error(`${t("goalsListComponent.goalDeleteErrorMessage")} - ${error}`);
	}
}
</script>