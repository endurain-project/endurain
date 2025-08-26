<template>
    <div class="col">
        <div class="bg-body-tertiary rounded p-3 shadow-sm">
            <!-- add goal button -->
            <a class="w-100 btn btn-primary" href="#" role="button" data-bs-toggle="modal"
                data-bs-target="#addGoalModal">{{ $t("settingsGoalsZone.addNewGoal") }}</a>

            <!-- Modal goal user -->
            <GoalsAddEditGoalModalComponent :action="'add'" @createdGoal="addGoalList"
                @isLoadingNewGoal="setIsLoadingNewGoal" />
            <LoadingComponent v-if="isLoading" />
            <div v-else>
                <div class="mt-3" v-if="goalsArray && goalsArray.length">
                    <span>{{ $t("settingsGoalsZone.labelNumberOfGoals1") }}{{ goalsArray.length }}{{
                            $t("settingsGoalsZone.labelNumberOfGoals2") }}</span>
                    <!-- Displaying loading new goal if applicable -->
                    <ul class="list-group list-group-flush" v-if="isLoadingNewGoal">
                        <li class="list-group-item rounded">
                            <LoadingComponent />
                        </li>
                    </ul>
                    <!-- list zone -->
                    <ul class="list-group list-group-flush" v-for="goal in goalsArray" :key="goal.id" :goal="goal" v-if="goalsArray && goalsArray.length">
                        <GoalsListComponent :goal="goal" />
                    </ul>
                </div>
                <NoItemsFoundComponents :show-shadow="false" v-else/>
            </div>
        </div>
    </div>
</template>

<script setup>
import { useI18n } from "vue-i18n";
import { ref, onMounted } from 'vue';
import { push } from "notivue";

import LoadingComponent from "@/components/GeneralComponents/LoadingComponent.vue";
import NoItemsFoundComponents from "@/components/GeneralComponents/NoItemsFoundComponents.vue";
import GoalsAddEditGoalModalComponent from "@/components/Settings/SettingsGoalsZone/GoalsAddEditGoalModalComponent.vue";
import GoalsListComponent from "@/components/Settings/SettingsGoalsZone/GoalsListComponent.vue";

import { userGoals as userGoalService } from '@/services/userGoalsService';

const { t } = useI18n();

const goalsArray = ref([]);
const isLoading = ref(true);
const isLoadingNewGoal = ref(false);

function setIsLoadingNewGoal(state) {
	isLoadingNewGoal.value = state;
}

onMounted(() => {
    userGoalService.getUserGoals().then((data) => {
        goalsArray.value = data;
    }).catch((error) => {
        push.error(`${t('settingsGoalsZone.errorFetchingGoals')} - ${error}`);
    });
	isLoading.value = false;
});
</script>