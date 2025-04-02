<template>
    <li class="list-group-item d-flex justify-content-between px-0 bg-body-tertiary">
        <div class="d-flex align-items-center">
            <img src="/src/assets/avatar/bicycle1.png" alt="Bycicle avatar" width="55" height="55" v-if="gear.gear_type == 1">
            <img src="/src/assets/avatar/running_shoe1.png" alt="Bycicle avatar" width="55" height="55" v-else-if="gear.gear_type == 2">
            <img src="/src/assets/avatar/wetsuit1.png" alt="Bycicle avatar" width="55" height="55" v-else>
            <div class="ms-3">
                <div class="fw-bold">
                    <router-link :to="{ name: 'gear', params: { id: gear.id }}" class="link-body-emphasis link-underline-opacity-0 link-underline-opacity-100-hover">
                        {{ gear.nickname }}
                    </router-link>
                </div>
                <b>{{ $t("gearsListComponent.gearListTypeLabel") }}: </b>
                <span v-if="gear.gear_type == 1">{{ $t("gearsListComponent.gearListTypeOption1") }}</span>
                <span v-else-if="gear.gear_type == 2">{{ $t("gearsListComponent.gearListTypeOption2") }}</span>
                <span v-else-if="gear.gear_type == 3">{{ $t("gearsListComponent.gearListTypeOption3") }}</span>
                <span v-else>{{ $t("gearsListComponent.gearListTypeOption4") }}</span>
                <br>
            </div>
        </div>
        <div>
            <span class="badge bg-danger-subtle border border-danger-subtle text-danger-emphasis align-middle d-none d-md-inline me-4" v-if="gear.is_active == 0">{{ $t("gearsListComponent.gearListGearIsInactiveBadge") }}</span>
            <!--<span class="badge bg-primary-subtle border border-primary-subtle text-primary-emphasis align-middle d-none d-lg-inline ms-2" v-if="gear.strava_gear_id">{{ $t("gearsListComponent.gearListGearFromStrava") }}</span>-->
            <span class="align-middle me-4 d-none d-sm-inline" v-if="gear.strava_gear_id">
                <font-awesome-icon :icon="['fab', 'fa-strava']" />
            </span>
            <!--<span class="badge bg-primary-subtle border border-primary-subtle text-primary-emphasis align-middle d-none d-lg-inline ms-2" v-if="gear.garminconnect_gear_id">{{ $t("gearsListComponent.gearListGearFromGarminConnect") }}</span>-->
            <span class="align-middle me-3 d-none d-sm-inline" v-if="gear.garminconnect_gear_id">
                <img src="/src/assets/garminconnect/Garmin_Connect_app_1024x1024-02.png" alt="Garmin Connect logo" height="22" />
            </span>

            <!-- edit gear button -->
            <a class="btn btn-link btn-lg link-body-emphasis d-none d-sm-inline" href="#" role="button" data-bs-toggle="modal" :data-bs-target="`#editGearModal${gear.id}`"><font-awesome-icon :icon="['fas', 'fa-pen-to-square']" /></a>

            <GearsAddEditGearModalComponent :action="'edit'" :gear="gear" @editedGear="editGearList"/>

            <!-- delete gear button -->
            <a class="btn btn-link btn-lg link-body-emphasis d-none d-sm-inline" href="#" role="button" data-bs-toggle="modal" :data-bs-target="`#deleteGearModal${gear.id}`"><font-awesome-icon :icon="['fas', 'fa-trash-can']" /></a>

            <!-- delete gear modal -->
            <ModalComponent :modalId="`deleteGearModal${gear.id}`" :title="t('gearsListComponent.gearListModalDeleteGearTitle')" :body="`${t('gearsListComponent.gearListModalDeleteGearBody')}<b>${gear.nickname}</b>?`" :actionButtonType="`danger`" :actionButtonText="t('gearsListComponent.gearListModalDeleteGearTitle')" @submitAction="submitDeleteGear"/>
        </div>
    </li>
</template>

<script>
import { useI18n } from "vue-i18n";
// Importing the services
import { gears } from '@/services/gearsService';
// Import Notivue push
import { push } from "notivue";
// Importing the components
import ModalComponent from "@/components/Modals/ModalComponent.vue";
import GearsAddEditGearModalComponent from "@/components/Gears/GearsAddEditGearModalComponent.vue";

export default {
	components: {
		ModalComponent,
		GearsAddEditGearModalComponent,
	},
	props: {
		gear: {
			type: Object,
			required: true,
		},
	},
	emits: ["gearDeleted", "editedGear"],
	setup(props, { emit }) {
		const { t } = useI18n();

        async function submitDeleteGear() {
			try {
                // Call the deleteGear method from the gears service.
				await gears.deleteGear(props.gear.id);

                // Emit the event to notify the parent component that the gear was deleted.
				emit("gearDeleted", props.gear.id);

                // Show the success alert.
                push.success(t("gearsListComponent.gearListGearDeleteSuccessMessage"));
			} catch (error) {
				// If there is an error, set the error message and show the error alert.
				push.error(
					`${t("gearsListComponent.gearListGearDeleteErrorMessage")} - ${error}`,
				);
			}
		}

        function editGearList(editedGear) {
			emit("editedGear", editedGear);
		}

        return {
			t,
			submitDeleteGear,
            editGearList,
		};
	},
};
</script>