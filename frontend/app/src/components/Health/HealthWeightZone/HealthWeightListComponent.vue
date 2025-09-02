<template>
    <li class="list-group-item d-flex justify-content-between p-0 bg-body-tertiary">
        <div class="d-flex align-items-center">
            <font-awesome-icon :icon="['fas', 'weight']" size="2x" />
            <div class="ms-3">
                <div class="fw-bold">
                    <span v-if="Number(authStore?.user?.units) === 1">{{ data.weight }} {{ $t("generalItems.unitsKg") }}</span>
                    <span v-else>{{ kgToLbs(data.weight) }} {{ $t("generalItems.unitsLbs") }}</span>
                </div>
                <span>
                    Date: {{ formatDateShort(data.date) }}
                    <span v-if="data.bmi"> | BMI: {{ data.bmi.toFixed(2) }}</span>
                </span>
            </div>
        </div>
        <div>
            <!--<span class="badge bg-primary-subtle border border-primary-subtle text-primary-emphasis align-middle ms-2" v-if="data.garminconnect_body_composition_id">{{ $t("healthWeightListComponent.labelGarminConnect") }}</span>-->
            <span class="align-middle me-3 d-none d-sm-inline" v-if="data.garminconnect_body_composition_id">
                <img src="/src/assets/garminconnect/Garmin_Connect_app_1024x1024-02.png" alt="Garmin Connect logo" height="22" />
            </span>

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
// Importing the stores
import { useAuthStore } from "@/stores/authStore";
// Import Notivue push
import { push } from "notivue";
// Importing the services
import { health_data } from "@/services/health_dataService";
// Import the components
import HealthWeightAddEditModalComponent from './HealthWeightAddEditModalComponent.vue';
import ModalComponent from '@/components/Modals/ModalComponent.vue';

import { formatDateShort } from "@/utils/dateTimeUtils";
import { kgToLbs } from "@/utils/unitsUtils";

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
		const authStore = useAuthStore();

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
            authStore,
            updateWeightListEdited,
            submitDeleteWeight,
            formatDateShort,
            kgToLbs,
		};
	},
};
</script>