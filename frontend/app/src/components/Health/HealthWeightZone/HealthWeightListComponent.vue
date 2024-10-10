<template>
    <li class="list-group-item d-flex justify-content-between">
        <div class="d-flex align-items-center">
            <font-awesome-icon :icon="['fas', 'weight']"     size="2x" />
            <div class="ms-3">
                <div class="fw-bold">
                    {{ data.weight }}
                </div>
                {{ formatDate(data.created_at) }}
            </div>
        </div>
        <div>
            <!-- edit weight button -->
            <a class="btn btn-link btn-lg link-body-emphasis" href="#" role="button" data-bs-toggle="modal" :data-bs-target="`#editWeightId${data.id}`"><font-awesome-icon :icon="['fas', 'fa-pen-to-square']" /></a>

            <HealthWeightAddEditModalComponent :action="'edit'" :data="data" @editedWeight="updateWeightListEdited" />

            <!-- delete weight button -->
            <a class="btn btn-link btn-lg link-body-emphasis" href="#" role="button" data-bs-toggle="modal" :data-bs-target="`#deleteWeightModal${data.id}`"><font-awesome-icon :icon="['fas', 'fa-trash-can']" /></a>

            <ModalComponent :modalId="`deleteWeightModal${data.id}`" :title="t('healthWeightListComponent.modalDeleteWeightTitle')" :body="`${t('healthWeightListComponent.modalDeleteWeightBody')}<b>${data.created_at}</b>?`" :actionButtonType="`danger`" :actionButtonText="t('healthWeightListComponent.modalDeleteWeightTitle')" @submitAction="submitDeleteWeight"/>
        </div>
    </li>
</template>

<script>
import { useI18n } from "vue-i18n";
// Import Notivue push
import { push } from "notivue";
// Importing the services
import { health_data } from "@/services/health_dataService";

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

        function updateWeightListEdited(editedWeight){
            emit("editedWeight", editedWeight);
        }

        async function submitDeleteWeight(){
            try {
                await health_data.deleteWeight(props.data.id);

                emit("deletedWeight", props.data.id);

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