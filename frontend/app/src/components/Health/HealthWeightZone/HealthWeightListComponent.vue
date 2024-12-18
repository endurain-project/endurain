<template>
    <li class="list-group-item d-flex justify-content-between">
        <div class="d-flex align-items-center">
            <font-awesome-icon :icon="['fas', 'weight']"     size="2x" />
            <div class="ms-3">
                <div class="fw-bold">
                    {{ data.weight }}
                </div>
                Date: {{ formatDate(data.date) }}<span v-if="data.bmi"> | BMI: {{ data.bmi }}</span>
            </div>
        </div>
        <div>
            <!-- edit weight button -->
            <a class="btn btn-link btn-lg link-body-emphasis" href="#" role="button" data-bs-toggle="modal" :data-bs-target="`#editWeightId${data.id}`"><font-awesome-icon :icon="['fas', 'fa-pen-to-square']" /></a>

            <HealthWeightAddEditModalComponent :action="'edit'" :data="data" @editedWeight="updateWeightListEdited" />

            <!-- delete weight button -->
            <a class="btn btn-link btn-lg link-body-emphasis" href="#" role="button" data-bs-toggle="modal" :data-bs-target="`#deleteWeightModal${data.id}`"><font-awesome-icon :icon="['fas', 'fa-trash-can']" /></a>

            <ModalComponent :modalId="`deleteWeightModal${data.id}`" :title="t('healthWeightListComponent.modalDeleteWeightTitle')" :body="`${t('healthWeightListComponent.modalDeleteWeightBody')}<b>${data.date}</b>?`" :actionButtonType="`danger`" :actionButtonText="t('healthWeightListComponent.modalDeleteWeightTitle')" @submitAction="submitDeleteWeight"/>
        </div>
    </li>
</template>

<script>
import { useI18n } from "vue-i18n";
// Import Notivue push
import { push } from "notivue";
// Importing the services
import { health_data } from "@/services/health_dataService";
// Import the components
import HealthWeightAddEditModalComponent from './HealthWeightAddEditModalComponent.vue';
import ModalComponent from '@/components/Modals/ModalComponent.vue';

export default {
	components: {
        HealthWeightAddEditModalComponent,
        ModalComponent,
	},
	props: {
		data: {
			type: Object,
			required: true,
		},
	},
    emits: ["editedWeight", "deletedWeight"],
	setup(props, { emit } ) {
		const { t } = useI18n();
        const formatDate = (dateString) => {
            const date = new Date(dateString);
            return `${date.getDate().toString().padStart(2, '0')}-${(date.getMonth() + 1).toString().padStart(2, '0')}-${date.getFullYear()}`;
        };

        async function updateWeightListEdited(editedWeight){
            try {
                await health_data.editHealthData(editedWeight);

                emit("editedWeight", editedWeight);

                push.success(t("healthWeightListComponent.successEditWeight"));
            } catch (error) {
                push.error(`${t("healthWeightListComponent.errorEditWeight")} - ${error.toString()}`);
            }
        }

        async function submitDeleteWeight(){
            try {
                const data = {
                    id: props.data.id,
                    user_id: props.data.user_id,
                    weight: null,
                    bmi: null,
                };
                await health_data.editHealthData(data);

                emit("deletedWeight", data.id);

                push.success(t("healthWeightListComponent.successDeleteWeight"));
            } catch (error) {
                push.error(`${t("healthWeightListComponent.errorDeleteWeight")} - ${error.toString()}`);
            }
        }

		return {
            t,
            formatDate,
            updateWeightListEdited,
            submitDeleteWeight,
		};
	},
};
</script>