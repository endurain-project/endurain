    <template>
        <ConfirmComponent 
            ref="confirmComponent" 
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
                        <di v class="card-header d-flex justify-content-between align-items-center">
                            <h5 class="card-title">{{ $t("settingsGoalsComponent.goalTitle", {index: index + 1}) }}</h5>
                            <button class="btn btn-danger" @click="deleteGoal(index)">
                                <font-awesome-icon :icon="['fas', 'fa-trash']" />
                            </button>
                        </di>
                        <div class="card-body">
                            <h5 class="card-title">{{ goal.title }}</h5>
                            <form>
                                <div class="mb-3">
                                    <label for="exampleInputEmail1" class="form-label">Activity Type</label>
                                    <select class="form-select" aria-label="Default select example">
                                        <option selected>Open this select menu</option>
                                        <option value="1">One</option>
                                        <option value="2">Two</option>
                                        <option value="3">Three</option>
                                    </select>
                                </div>
                                <div class="mb-3">
                                    <label for="exampleInputPassword1" class="form-label">Password</label>
                                    <input type="password" class="form-control" id="exampleInputPassword1">
                                </div>
                                <button type="submit" class="btn btn-primary">Submit</button>
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

    import ConfirmComponent from '@/components/GeneralComponents/ConfirmComponent.vue';
    import {activityList} from '@/utils/activityUtils';

    export default {
        components: {
            ConfirmComponent
        },
        name: 'SettingsGoals',
        setup() {
            const { t } = useI18n();

            // Setup logic can go here if needed

            const goals = ref([]);
            const confirmComponent = ref(null);

            const addGoal = () => {
                // Logic to add a new goal
                const newGoal = {}
                
                goals.value.push(newGoal);
            };

            const deleteGoal = (index) => {
                console.log(confirmComponent.value.show)
                // confirmComponent.value.show();

                // Logic to delete a goal
                // goals.value.splice(index, 1);
            };

            return {
                t,

                // Reactive properties
                goals,
                confirmComponent,
                activityList,

                // Methods
                addGoal,
                deleteGoal
            }
        },
    };
    </script>