    <template>
        <ConfirmComponent 
            ref="confirmComponent"
            @confirm="deleteGoalAction"
            :title="$t('settingsGoalsComponent.deleteGoalConfirm')"  />
        <div class="col">
            <div class="bg-body-tertiary rounded p-3 shadow-sm">
                <button
                    @click="addGoal" 
                    type="button" 
                    class="btn btn-primary">
                    <font-awesome-icon :icon="['fas', 'fa-plus']" />
                </button>                           
                <div v-for="(goal, index) in goals" class="mt-3">
                    <div class="card mb-2">
                        <div class="card-header d-flex justify-content-between align-items-center">
                            <h5 class="card-title">{{ $t("settingsGoalsComponent.goalTitle", {index: index + 1}) }}</h5>
                            <button class="btn btn-danger" @click="deleteGoal(index)">
                                <font-awesome-icon :icon="['fas', 'fa-trash']" />
                            </button>
                        </div>
                        <div class="card-body">
                            <h5 class="card-title">{{ goal.title }}</h5>
                            <form :id="`form-goal-${index}`" @submit.prevent="updateGoal(index, goal)">
                                <div class="mb-3">
                                    <label for="exampleInputEmail1" class="form-label">Interval</label>
                                    <select class="form-select" aria-label="Interval" id="interval" name="interval">
                                        <option 
                                            v-for="(value, key) in goalIntervalList"
                                            :selected="key == goal.interval" 
                                            :value="key">
                                            {{t(value)}}
                                        </option>
                                    </select>
                                </div>
                                <div class="mb-3">
                                    <label for="exampleInputEmail1" class="form-label">Activity Type</label>
                                    <select class="form-select" aria-label="activity type" name="activity_type" id="activity_type">
                                        <option 
                                            v-for="(value, key) in activityList"
                                            :selected="key == goal.activity_type" 
                                            :value="key">
                                            {{value}}
                                        </option>
                                    </select>
                                </div>
                                <div class="mb-3">
                                    <label for="goal_calories" class="form-label">Calories</label>
                                    <input type="number" class="form-control" id="goal_calories" name="goal_calories" :value="goal.goal_calories" >
                                    <div class="form-text">
                                        {{ $t("settingsGoalsComponent.goalCaloriesDescription") }}
                                    </div>
                                </div>
                                <div class="mb-3">
                                    <label for="goal_count" class="form-label">Activities</label>
                                    <input type="number" class="form-control" id="goal_count" name="goal_count" :value="goal.goal_count" >
                                    <div class="form-text">
                                        {{ $t("settingsGoalsComponent.goalActivitiesDescription") }}
                                    </div>
                                </div>
                                <div class="mb-3">
                                    <label for="goal_distance" class="form-label">Distance</label>
                                    <input type="number" class="form-control" id="goal_distance" name="goal_distance" :value="goal.goal_distance" >
                                    <div class="form-text">
                                        {{ $t("settingsGoalsComponent.goalDistanceDescription") }}
                                    </div>
                                </div>
                                <div class="mb-3">
                                    <label for="goal_duration" class="form-label">Duration</label>
                                    <input type="text" class="form-control" id="goal_duration" name="goal_duration" :value="goal.goal_duration" >
                                    <div class="form-text">
                                        {{ $t("settingsGoalsComponent.goalDurationDescription") }}
                                    </div>
                                </div>
                                <div class="mb-3">
                                    <label for="goal_elevation" class="form-label">Elevation</label>
                                    <input type="number" class="form-control" id="goal_elevation" name="goal_elevation" :value="goal.goal_elevation" >
                                    <div class="form-text">
                                        {{ $t("settingsGoalsComponent.goalElevationDescription") }}
                                    </div>
                                </div>
                                <button type="submit" class="btn btn-primary">Save</button>
                            </form>
                        </div>
                    </div>
                </div>
            </div>
        </div>
    </template>

    <script>

    import { useI18n } from "vue-i18n";
    import { ref } from 'vue';
    import { push } from "notivue";
    import parseDuration from 'parse-duration'


    import ConfirmComponent from '@/components/GeneralComponents/ConfirmComponent.vue';
    import {activityList, goalIntervalList} from '@/utils/activityUtils';

    import { userGoals as userGoalService } from '@/services/userGoalsService';

    export default {
        components: {
            ConfirmComponent
        },
        name: 'SettingsGoals',
        setup() {
            const { t } = useI18n();

            // Setup logic can go here if needed

            const goals = ref([]);
            const selectedGoalToDeleteIndex = ref(null);
            const confirmComponent = ref(null);

            userGoalService.getUserGoals().then((data) => {
                goals.value = data;
            }).catch((error) => {
                push.error(`${t('settingsGoalsComponent.errorFetchingGoals')} - ${error}`);
            });

            const addGoal = () => {
                // Logic to add a new goal
                const newGoal = {}
                
                goals.value.push(newGoal);
            };

            const deleteGoal = (index) => {
                confirmComponent.value.show();
                selectedGoalToDeleteIndex.value = index;
            };

            const deleteGoalAction = () => {
                const index = selectedGoalToDeleteIndex.value
                const goalToDelete = goals.value[index];

                if (!goalToDelete.id) {
                    goals.value.splice(index, 1);
                    return;
                }

                userGoalService.deleteGoal(goalToDelete.id).then(() => {
                    // Remove the goal from the local state
                    goals.value.splice(index, 1);
                    push.success(t('settingsGoalsComponent.goalDeleted'));
                }).catch((error) => {
                    push.error(`${t('settingsGoalsComponent.errorUpdatingGoal')} - ${error}`);
                });
            };

            const updateGoal = (index, updatedGoal) => {
                const existingGoal = goals.value[index];

                const form = document.getElementById(`form-goal-${index}`)
                const newValues = Object.keys(Object.fromEntries(new FormData(form)))
                    .reduce((acc, key) => {
                        acc[key] = form[key].value;

                        if (acc[key].match(/^\d+$/g)) {
                            acc[key] = parseInt(acc[key]);
                        }

                        if (key === 'goal_duration') {
                            acc[key] = parseDuration(acc[key]) / 1000; // Convert to seconds
                        }

                        return acc;
                    }, {});

                if (!existingGoal.id) {
                    userGoalService.createGoal(newValues).then((data) => {
                        // Add the new goal to the local state
                        existingGoal.id = data.id;
                        push.success(t('settingsGoalsComponent.goalUpdated'));
                    }).catch((error) => {
                        push.error(`${t('settingsGoalsComponent.errorUpdatingGoal')} - ${error}`);
                    });
                    return;
                }

                userGoalService.updateGoal(existingGoal.id, {...existingGoal, ...newValues}).then((data) => {
                    // Update the goal in the local state
                    goals.value[index] = data;
                    push.success(t('settingsGoalsComponent.goalUpdated'));
                }).catch((error) => {
                    push.error(`${t('settingsGoalsComponent.errorUpdatingGoal')} - ${error}`);
                });
            };

            return {
                t,

                // Reactive properties
                goals,
                confirmComponent,
                activityList,
                goalIntervalList,

                // Methods
                addGoal,
                deleteGoal,
                updateGoal,
                deleteGoalAction
            }
        },
    };
    </script>