<template>
    <div class="modal fade" 
     :id="action === 'add' ? 'addGearModal' : (action === 'edit' ? editGearModalId : null)"
     tabindex="-1" 
     :aria-labelledby="action === 'add' ? 'addGearModal' : (action === 'edit' ? editGearModalId : null)"
     ref="addEditGearModal"
     aria-hidden="true">
        <div class="modal-dialog">
            <div class="modal-content">
                <div class="modal-header">
                    <h1 class="modal-title fs-5" id="addGearModal" v-if="action === 'add'">{{ $t("gearsAddEditGearModalComponent.addEditGearModalAddTitle") }}</h1>
                    <h1 class="modal-title fs-5" :id='editGearModalId' v-else>{{ $t("gearsAddEditGearModalComponent.addEditGearModalEditTitle") }}</h1>
                    <button type="button" class="btn-close" data-bs-dismiss="modal" aria-label="Close"></button>
                </div>
                <form @submit.prevent="handleSubmit">
                    <div class="modal-body">
                        <!-- brand fields -->
                        <label for="gearBrandAddEdit"><b>{{ $t("gearsAddEditGearModalComponent.addEditGearModalAddBrandLabel") }}</b></label>
                        <input class="form-control" type="text" name="gearBrandAddEdit" :placeholder='$t("gearsAddEditGearModalComponent.addEditGearModalAddBrandLabel")' v-model="newEditGearBrand" maxlength="250">
                        <!-- model fields -->
                        <label for="gearModelAddEdit"><b>{{ $t("gearsAddEditGearModalComponent.addEditGearModalAddModelLabel") }}</b></label>
                        <input class="form-control" type="text" name="gearModelAddEdit" :placeholder='$t("gearsAddEditGearModalComponent.addEditGearModalAddModelLabel")' v-model="newEditGearModel" maxlength="250">
                        <!-- nickname fields -->
                        <label for="gearNicknameAddEdit"><b>* {{ $t("gearsAddEditGearModalComponent.addEditGearModalAddNicknameLabel") }}</b></label>
                        <input class="form-control" :class="{ 'is-invalid': !isNicknameExists }" type="text" name="gearNicknameAddEdit" :placeholder='$t("gearsAddEditGearModalComponent.addEditGearModalAddNicknameLabel")' v-model="newEditGearNickname" maxlength="250" required>
                        <div id="validationNicknameFeedback" class="invalid-feedback" v-if="!isNicknameExists">
                            {{ $t("gearsAddEditGearModalComponent.errorNicknameAlreadyExistsFeedback") }}
                        </div>
                        <!-- gear type fields -->
                        <label for="gearTypeAddEdit"><b>* {{ $t("gearsAddEditGearModalComponent.addEditGearModalAddTypeLabel") }}</b></label>
                        <select class="form-select" name="gearTypeAddEdit" v-model="newEditGearType" required>
                            <option value="1">{{ $t("gearsAddEditGearModalComponent.addEditGearModalAddTypeOption1") }}</option>
                            <option value="2">{{ $t("gearsAddEditGearModalComponent.addEditGearModalAddTypeOption2") }}</option>
                            <option value="3">{{ $t("gearsAddEditGearModalComponent.addEditGearModalAddTypeOption3") }}</option>
                        </select>
                        <!-- date fields -->
                        <label for="gearDateAddEdit"><b>* {{ $t("gearsAddEditGearModalComponent.addEditGearModalAddDateLabel") }}</b></label>
                        <input class="form-control" type="date" name="gearDateAddEdit" v-model="newEditGearCreatedDate" required>
                        <!-- gear is_active fields -->
                        <label for="gearIsActiveAddEdit"><b>* {{ $t("gearsAddEditGearModalComponent.addEditGearModalAddIsActiveLabel") }}</b></label>
                        <select class="form-select" name="gearIsActiveAddEdit" v-model="newEditGearIsActive" required>
                            <option value="1">{{ $t("gearsAddEditGearModalComponent.addEditGearModalAddIsActiveOption1") }}</option>
                            <option value="0">{{ $t("gearsAddEditGearModalComponent.addEditGearModalAddIsActiveOption0") }}</option>
                        </select>
                        <!-- initial kilometers fields -->
                        <div v-if="Number(authStore?.user?.units) === 1">
                            <label for="gearInitialKmsAddEdit"><b>* {{ $t("gearsAddEditGearModalComponent.addEditGearModalAddIsInitialKmsLabel") }}</b></label>
                            <input class="form-control" type="number" step="0.1" name="gearInitialKmsAddEdit" v-model="newEditGearInitialKms" required>
                        </div>
                        <!-- initial miles fields -->
                        <div v-else>
                            <label for="gearInitialMilesAddEdit"><b>* {{ $t("gearsAddEditGearModalComponent.addEditGearModalAddIsInitialMilesLabel") }}</b></label>
                            <input class="form-control" type="number" step="0.1" name="gearInitialMilesAddEdit" v-model="newEditGearInitialMiles" required>
                        </div>
                        
                        <p>* {{ $t("generalItems.requiredField") }}</p>
                    </div>
                    <div class="modal-footer">
                        <button type="button" class="btn btn-secondary" data-bs-dismiss="modal">{{ $t("generalItems.buttonClose") }}</button>
                        <button type="submit" class="btn btn-success" name="addGear" data-bs-dismiss="modal" v-if="action === 'add'" :disabled="!isNicknameExists || !newEditGearCreatedDate || !newEditGearNickname">{{ $t("gearsAddEditGearModalComponent.addEditGearModalAddTitle") }}</button>
                        <button type="submit" class="btn btn-success" name="editGear" data-bs-dismiss="modal" v-else :disabled="!isNicknameExists || !newEditGearCreatedDate || !newEditGearNickname">{{ $t("gearsAddEditGearModalComponent.addEditGearModalEditTitle") }}</button>
                    </div>
                </form>
            </div>
        </div>
    </div>
</template>

<script>
import { ref, watch, onMounted } from "vue";
import { useI18n } from "vue-i18n";
// Import the stores
import { useAuthStore } from "@/stores/authStore";
// import lodash
import { debounce } from 'lodash';
// Import Notivue push
import { push } from "notivue";
// Importing the services
import { gears } from '@/services/gearsService';
// Import units utils
import { kmToMiles, milesToKm } from "@/utils/unitsUtils";
// Importing the utils
import { removeActiveModal, resetBodyStylesIfNoActiveModals } from "@/utils/modalUtils";
// Importing the bootstrap modal
import Modal from 'bootstrap/js/src/modal';

export default {
    props: {
		action: {
			type: String,
			required: true,
		},
		gear: {
			type: Object,
			required: false,
		},
	},
    emits: ["isLoadingNewGear", "createdGear", "editedGear"],
    setup(props, { emit }) {
		const authStore = useAuthStore();
		const { t } = useI18n();
        // edit gear specific variables
		const editGearModalId = ref("");
        const newEditGearBrand = ref('');
        const newEditGearModel = ref('');
        const newEditGearNickname = ref('');
        const newEditGearType = ref(1);
        const newEditGearCreatedDate = ref(null);
		const newEditGearIsActive = ref(1);
        const newEditGearInitialKms = ref(0);
        const newEditGearInitialMiles = ref(0);
        const isNicknameExists = ref(true);
        const validateNicknameExists = debounce(async () => {
            let tryValidate = false;
            if (props.action === 'edit') {
                if (newEditGearNickname.value !== props.gear.nickname) {
                    tryValidate = true;
                }
            } else {
                if (props.action === 'add') {
                    if (newEditGearNickname.value !== "") {
                        tryValidate = true;
                    }
                }
            }

            if (tryValidate) {
                try {
                    if (await gears.getGearByNickname(newEditGearNickname.value)) {
                        isNicknameExists.value = false;
                    } else {
                        isNicknameExists.value = true;
                    }
                } catch (error) {
                    push.error(`${t("gearsAddEditGearModalComponent.errorNotPossibleToGetGearByNickname")} - ${error}`);
                }
            } else {
                isNicknameExists.value = true;
            }
        }, 500);

        onMounted(() => {
            if (props.gear) {
                if (props.action === 'edit') {
                    editGearModalId.value = `editGearModal${props.gear.id}`;
                }
                newEditGearBrand.value = props.gear.brand;
                newEditGearModel.value = props.gear.model;
                newEditGearNickname.value = props.gear.nickname;
                newEditGearType.value = props.gear.gear_type;
                newEditGearCreatedDate.value = props.gear.created_at;
                newEditGearIsActive.value = props.gear.is_active;
                newEditGearInitialKms.value = props.gear.initial_kms;
                if (props.gear.initial_kms && props.gear.initial_kms !== 0) {
                    newEditGearInitialMiles.value = kmToMiles(props.gear.initial_kms);
                }
            }
        });


        async function submitAddGearForm() {
			// Set the loading variable to true.
			emit("isLoadingNewGear", true);
            try {
                // Create the gear data object.
                const data = {
                    brand: newEditGearBrand.value,
                    model: newEditGearModel.value,
                    nickname: newEditGearNickname.value,
                    gear_type: newEditGearType.value,
                    created_at: newEditGearCreatedDate.value,
					is_active: newEditGearIsActive.value,
                    initial_kms: newEditGearInitialKms.value,
                };

                // Create the gear and get the created gear id.
                const createdGear = await gears.createGear(data);

                // Set the loading variable to false.
                emit("isLoadingNewGear", false);

                // Get the created gear and add it to the array.
                emit("createdGear", createdGear);

                // Set the success message and show the success alert.
                push.success(t("gearsAddEditGearModalComponent.successGearAdded"));
            } catch (error) {
                // If there is an error, set the error message and show the error alert.
				push.error(`${t("gearsAddEditGearModalComponent.errorGearAdded")} - ${error}`);
            } finally {
                // Set the isLoadingNewGear variable to false.
                emit("isLoadingNewGear", false);
            }
        }

        async function submitEditGearForm() {
            try {
				const data = {
                    id: props.gear.id,
					brand: newEditGearBrand.value,
					model: newEditGearModel.value,
					nickname: newEditGearNickname.value,
					gear_type: newEditGearType.value,
					created_at: newEditGearCreatedDate.value,
					is_active: newEditGearIsActive.value,
                    initial_kms: newEditGearInitialKms.value,
				};

				await gears.editGear(props.gear.id, data);
                
                emit("editedGear", data);

				push.success(t("gearsAddEditGearModalComponent.successGearEdited"));
			} catch (error) {
				// If there is an error, set the error message and show the error alert.
				push.error(`${t("gearsAddEditGearModalComponent.errorGearEdited")} - ${error}`);
			}
        }


        function handleSubmit() {
            if (Number(authStore?.user?.units) === 1) {
                if ((props.gear && newEditGearInitialKms.value !== props.gear.initial_kms) || props.action === 'add') {
                    newEditGearInitialMiles.value = kmToMiles(newEditGearInitialKms.initial_kms);
                }
            } else {
                if (props.action === 'add') {
                    newEditGearInitialKms.value = milesToKm(newEditGearInitialMiles.value);
                } else {
                    const miles = kmToMiles(props.gear.initial_kms);
                    if (miles !== newEditGearInitialMiles.value) {
                        newEditGearInitialKms.value = milesToKm(newEditGearInitialMiles.value);
                    }
                }
            }
            
            if (props.action === 'add') {
                submitAddGearForm();
            } else {
                submitEditGearForm();
            }
        }

        // Watchers
        // Watch the newEditGearNickname variable.
        watch(newEditGearNickname, validateNicknameExists, { immediate: false });

        return {
            authStore,
			t,
            editGearModalId,
            newEditGearBrand,
            newEditGearModel,
            newEditGearNickname,
            newEditGearType,
            newEditGearCreatedDate,
            newEditGearIsActive,
            newEditGearInitialKms,
            newEditGearInitialMiles,
            handleSubmit,
            isNicknameExists,
		};
    },
};
</script>