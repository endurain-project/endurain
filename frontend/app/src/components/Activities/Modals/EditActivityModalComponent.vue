<template>
    <!-- Modal edit activity -->
    <div class="modal fade" id="editActivityModal" tabindex="-1" aria-labelledby="editActivityModalComponent" aria-hidden="true">
        <div class="modal-dialog">
            <div class="modal-content">
                <div class="modal-header">
                    <h1 class="modal-title fs-5" id="editActivityModal">{{ $t("editActivityModalComponent.modalEditActivityTitle") }}</h1>
                    <button type="button" class="btn-close" data-bs-dismiss="modal" aria-label="Close"></button>
                </div>
                <form  @submit.prevent="submitEditActivityForm">
                    <div class="modal-body">
                        <!-- name fields -->
                        <label for="activityNameEdit"><b>* {{ $t("editActivityModalComponent.modalEditActivityNameLabel") }}</b></label>
                        <input class="form-control" type="text" name="activityNameEdit" :placeholder='$t("editActivityModalComponent.modalEditActivityNamePlaceholder")' maxlength="45" v-model="editActivityName" required>
                        <!-- description fields -->
                        <label for="activityDescriptionEdit"><b>{{ $t("editActivityModalComponent.modalEditActivityDescriptionLabel") }}</b></label>
                        <input class="form-control" type="text" name="activityDescriptionEdit" :placeholder='$t("editActivityModalComponent.modalEditActivityDescriptionPlaceholder")' maxlength="2500" v-model="editActivityDescription">
                        <!-- type fields -->
                        <label for="activityTypeEdit"><b>* {{ $t("editActivityModalComponent.modalEditActivityTypeLabel") }}</b></label>
                        <select class="form-control" name="activityTypeEdit" v-model="editActivityType" required>
                            <option value="1">{{ $t("editActivityModalComponent.modalEditActivityTypeOption1") }}</option>
                            <option value="2">{{ $t("editActivityModalComponent.modalEditActivityTypeOption2") }}</option>
                            <option value="3">{{ $t("editActivityModalComponent.modalEditActivityTypeOption3") }}</option>
                            <option value="4">{{ $t("editActivityModalComponent.modalEditActivityTypeOption4") }}</option>
                            <option value="5">{{ $t("editActivityModalComponent.modalEditActivityTypeOption5") }}</option>
                            <option value="6">{{ $t("editActivityModalComponent.modalEditActivityTypeOption6") }}</option>
                            <option value="7">{{ $t("editActivityModalComponent.modalEditActivityTypeOption7") }}</option>
                            <option value="8">{{ $t("editActivityModalComponent.modalEditActivityTypeOption8") }}</option>
                            <option value="9">{{ $t("editActivityModalComponent.modalEditActivityTypeOption9") }}</option>
                            <option value="10">{{ $t("editActivityModalComponent.modalEditActivityTypeOption10") }}</option>
                            <option value="11">{{ $t("editActivityModalComponent.modalEditActivityTypeOption11") }}</option>
                            <option value="12">{{ $t("editActivityModalComponent.modalEditActivityTypeOption12") }}</option>
                        </select>
                        <!-- visibility fields -->
                        <label for="activityVisibilityEdit"><b>* {{ $t("editActivityModalComponent.modalEditActivityVisibilityLabel") }}</b></label>
                        <select class="form-control" name="activityVisibilityEdit" v-model="editActivityVisibility" required>
                            <option value="0">{{ $t("editActivityModalComponent.modalEditActivityVisibilityOption0") }}</option>
                            <option value="1">{{ $t("editActivityModalComponent.modalEditActivityVisibilityOption1") }}</option>
                            <option value="2">{{ $t("editActivityModalComponent.modalEditActivityVisibilityOption2") }}</option>
                        </select>
                        <p>* {{ $t("generalItens.requiredField") }}</p>
                    </div>
                    <div class="modal-footer">
                        <button type="button" class="btn btn-secondary" data-bs-dismiss="modal">{{ $t("generalItens.buttonClose") }}</button>
                        <button type="submit" class="btn btn-success" data-bs-dismiss="modal">{{ $t("editActivityModalComponent.modalEditActivityTitle") }}</button>
                    </div>
                </form>
            </div>
        </div>
    </div>
</template>

<script>
import { ref } from "vue";
import { useI18n } from "vue-i18n";
// Import Notivue push
import { push } from "notivue";
// Importing the services
import { activities } from "@/services/activitiesService";

export default {
	components: {},
	props: {
		activity: {
			type: Object,
			required: true,
		},
	},
	setup(props) {
		const { t } = useI18n();
		const editActivityDescription = ref(props.activity.description);
		const editActivityName = ref(props.activity.name);
		const editActivityType = ref(props.activity.activity_type);
		const editActivityVisibility = ref(props.activity.visibility);

		async function submitEditActivityForm() {
			try {
				const data = {
					id: props.activity.id,
					name: editActivityName.value,
					description: editActivityDescription.value,
					activity_type: editActivityType.value,
					visibility: editActivityVisibility.value,
				};

				// Call the service to edit the activity
				await activities.editActivity(props.activity.id, data);

				// Set activity new values
				props.activity.name = editActivityName.value;
				props.activity.description = editActivityDescription.value;
				props.activity.activity_type = editActivityType.value;
				props.activity.visibility = editActivityVisibility.value;

				// show success toast
                push.success(t("editActivityModalComponent.successActivityEdit"));
			} catch (error) {
				// If there is an error, set the error message and show the error alert.
				push.error(`${t("editActivityModalComponent.errorActivityEdit")} - ${error}`);
			}
		}

		return {
			editActivityDescription,
			editActivityName,
			editActivityType,
			editActivityVisibility,
			submitEditActivityForm,
		};
	},
};
</script>