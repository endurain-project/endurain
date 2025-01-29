<template>
    <!-- Modal add/edit user -->
    <div class="modal fade" :id="action == 'add' ? 'addUserModal' : (action == 'edit' ? editUserId : '')" tabindex="-1" :aria-labelledby="action == 'add' ? 'addUserModal' : (action == 'edit' ? editUserId : '')" aria-hidden="true">
        <div class="modal-dialog">
            <div class="modal-content">
                <div class="modal-header">
                    <h1 class="modal-title fs-5" id="addUserModal" v-if="action == 'add'">{{ $t("settingsUsersZone.buttonAddUser") }}</h1>
                    <h1 class="modal-title fs-5" id="editUserId" v-else>{{ $t("usersAddEditUserModalComponent.addEditUserModalEditTitle") }}</h1>
                    <button type="button" class="btn-close" data-bs-dismiss="modal" aria-label="Close"></button>
                </div>
                <form @submit.prevent="handleSubmit">
                    <div class="modal-body">
                        <label for="userImgAddEdit"><b>{{ $t("usersAddEditUserModalComponent.addEditUserModalUserPhotoLabel") }}</b></label>
                        <div>
                            <div class="row">
                                <div class="col">
                                    <input class="form-control" type="file" accept="image/*" name="userImgAddEdit" id="userImgAddEdit" @change="handleFileChange">
                                </div>
                                <div class="col" v-if="newEditUserPhotoPath">
                                    <a class="w-100 btn btn-danger" data-bs-dismiss="modal" @click="submitDeleteUserPhoto">{{ $t("usersAddEditUserModalComponent.addEditUserModalDeleteUserPhotoButton") }}</a>
                                </div>
                            </div>
                        </div>
                        <!-- username fields -->
                        <label for="userUsernameAddEdit"><b>* {{ $t("usersAddEditUserModalComponent.addEditUserModalUsernameLabel") }}</b></label>
                        <input class="form-control" type="text" name="userUsernameAddEdit" :placeholder='$t("usersAddEditUserModalComponent.addEditUserModalUsernamePlaceholder")' maxlength="250" v-model="newEditUserUsername" required>
                        <!-- name fields -->
                        <label for="userNameAddEdit"><b>* {{ $t("usersAddEditUserModalComponent.addEditUserModalNameLabel") }}</b></label>
                        <input class="form-control" type="text" name="userNameAddEdit" :placeholder='$t("usersAddEditUserModalComponent.addEditUserModalNamePlaceholder")' maxlength="250" v-model="newEditUserName" required>
                        <!-- email fields -->
                        <label for="userEmailAddEdit"><b>* {{ $t("usersAddEditUserModalComponent.addEditUserModalEmailLabel") }}</b></label>
                        <input class="form-control" type="text" name="userEmailAddEdit" :placeholder='$t("usersAddEditUserModalComponent.addEditUserModalEmailPlaceholder")' maxlength="45" v-model="newEditUserEmail" required>
                        <!-- password fields -->
                        <div v-if="action == 'add'">
                            <label for="passUserAdd"><b>* {{ $t("usersAddEditUserModalComponent.addEditUserModalPasswordLabel") }}</b></label>
                            <input class="form-control" :class="{ 'is-invalid': !isPasswordValid }" type="password" id="validationPassword" aria-describedby="validationPasswordFeedback" name="passUserAdd" :placeholder='$t("usersAddEditUserModalComponent.addEditUserModalPasswordPlaceholder")' v-model="newUserPassword" required>
                            <div id="validationPasswordFeedback" class="invalid-feedback" v-if="!isPasswordValid">
                                {{ $t("usersListComponent.modalChangeUserPasswordFeedbackLabel") }}
                            </div>
                        </div>
                        <!-- city fields -->
                        <label for="userCityAddEdit"><b>{{ $t("usersAddEditUserModalComponent.addEditUserModalCityLabel") }}</b></label>
                        <input class="form-control" type="text" name="userCityAddEdit" :placeholder='$t("usersAddEditUserModalComponent.addEditUserModalCityPlaceholder")' maxlength="45" v-model="newEditUserCity">
                        <!-- birth date fields -->
                        <label for="userBirthDateAddEdit"><b>{{ $t("usersAddEditUserModalComponent.addEditUserModalBirthdayLabel") }}</b></label>
                        <input class="form-control" type="date" name="userBirthDateAddEdit" v-model="newEditUserBirthDate">
                        <!-- gender fields -->
                        <label for="userGenderAddEdit"><b>* {{ $t("usersAddEditUserModalComponent.addEditUserModalGenderLabel") }}</b></label>
                        <select class="form-control" name="userGenderAddEdit" v-model="newEditUserGender" required>
                            <option value="1">{{ $t("usersAddEditUserModalComponent.addEditUserModalGenderOption1") }}</option>
                            <option value="2">{{ $t("usersAddEditUserModalComponent.addEditUserModalGenderOption2") }}</option>
                        </select>
                        <!-- units fields -->
                        <label for="userUnitsAddEdit"><b>* {{ $t("usersAddEditUserModalComponent.addEditUserModalUnitsLabel") }}</b></label>
                        <select class="form-control" name="userUnitsAddEdit" v-model="newEditUserUnits" required>
                            <option value="1">{{ $t("usersAddEditUserModalComponent.addEditUserModalUnitsOption1") }}</option>
                            <option value="2">{{ $t("usersAddEditUserModalComponent.addEditUserModalUnitsOption2") }}</option>
                        </select>
                        <!-- height fields -->
                        <div v-if="authStore.user.units == 1">
                            <label for="userHeightAddEditCms"><b>{{ $t("usersAddEditUserModalComponent.addEditUserModalHeightLabel") }} ({{ $t("generalItems.unitsCm") }})</b></label>
                            <input class="form-control" type="number" name="userHeightAddEditCms" :placeholder='$t("usersAddEditUserModalComponent.addEditUserModalHeightPlaceholder") + " (" + $t("generalItems.unitsCm") + ")"' v-model="newEditUserHeightCms">
                        </div>
                        <div v-else>
                            <label for="userHeightAddEditFeetInches"><b>{{ $t("usersAddEditUserModalComponent.addEditUserModalHeightLabel") }} ({{ $t("generalItems.unitsFeetInches") }})</b></label>
                            <div class="input-group">
                                <input class="form-control" :class="{ 'is-invalid': !isFeetValid }" type="number" aria-describedby="validationFeetFeedback" name="userHeightAddEditFeet" :placeholder='$t("usersAddEditUserModalComponent.addEditUserModalHeightPlaceholder") + " (" + $t("generalItems.unitsFeet") + ")"' v-model="newEditUserHeightFeet" min="0" max="10" step="1">
                                <span class="input-group-text">’</span>
                                <input class="form-control" :class="{ 'is-invalid': !isInchesValid }" type="number" aria-describedby="validationInchesFeedback" name="userHeightAddEditInches" :placeholder='$t("usersAddEditUserModalComponent.addEditUserModalHeightPlaceholder") + " (" + $t("generalItems.unitsInches") + ")"' v-model="newEditUserHeightInches" min="0" max="11" step="1">
                                <span class="input-group-text">’’</span>
                                <div id="validationFeetFeedback" class="invalid-feedback" v-if="!isFeetValid">
                                    {{ $t("usersAddEditUserModalComponent.addEditUserModalFeetValidationLabel") }}
                                </div>
                                <div id="validationInchesFeedback" class="invalid-feedback" v-if="!isInchesValid">
                                    {{ $t("usersAddEditUserModalComponent.addEditUserModalInchesValidationLabel") }}
                                </div>
                            </div>
                        </div>
                        <!-- preferred language fields -->
                        <label for="userPreferredLanguageAddEdit"><b>* {{ $t("usersAddEditUserModalComponent.addEditUserModalUserPreferredLanguageLabel") }}</b></label>
                        <select class="form-control" name="userPreferredLanguageAddEdit" v-model="newEditUserPreferredLanguage" required>
                            <option value="us">{{ $t("usersAddEditUserModalComponent.addEditUserModalPreferredLanguageOption1") }}</option>
                            <option value="ca">{{ $t("usersAddEditUserModalComponent.addEditUserModalPreferredLanguageOption2") }}</option>
                            <option value="pt">{{ $t("usersAddEditUserModalComponent.addEditUserModalPreferredLanguageOption3") }}</option>
                            <option value="de">{{ $t("usersAddEditUserModalComponent.addEditUserModalPreferredLanguageOption4") }}</option>
                            <option value="fr">{{ $t("usersAddEditUserModalComponent.addEditUserModalPreferredLanguageOption5") }}</option>
                        </select>
                        <!-- access type fields -->
                        <label for="userTypeAddEdit"><b>* {{ $t("usersAddEditUserModalComponent.addEditUserModalUserTypeLabel") }}</b></label>
                        <select class="form-control" name="userTypeAddEdit" v-model="newEditUserAccessType" required>
                            <option value="1">{{ $t("usersAddEditUserModalComponent.addEditUserModalUserTypeOption1") }}</option>
                            <option value="2">{{ $t("usersAddEditUserModalComponent.addEditUserModalUserTypeOption2") }}</option>
                        </select>
                        <!-- user is_active fields -->
                        <label for="userIsActiveAddEdit"><b>* {{ $t("usersAddEditUserModalComponent.addEditUserModalIsActiveLabel") }}</b></label>
                        <select class="form-control" name="userIsActiveAddEdit" v-model="newEditUserIsActive" required>
                            <option value="1">{{ $t("usersAddEditUserModalComponent.addEditUserModalIsActiveOption1") }}</option>
                            <option value="2">{{ $t("usersAddEditUserModalComponent.addEditUserModalIsActiveOption2") }}</option>
                        </select>

                        <p>* {{ $t("generalItems.requiredField") }}</p>
                    </div>
                    <div class="modal-footer">
                        <button type="button" class="btn btn-secondary" data-bs-dismiss="modal">{{ $t("generalItems.buttonClose") }}</button>
                        <button type="submit" class="btn btn-success" name="userAdd" data-bs-dismiss="modal" v-if="action == 'add'" :disabled="!isPasswordValid">{{ $t("usersAddEditUserModalComponent.addEditUserModalAddTitle") }}</button>
                        <button type="submit" class="btn btn-success" name="userEdit" data-bs-dismiss="modal" v-else :disabled="!isFeetValid || !isInchesValid">{{ $t("usersAddEditUserModalComponent.addEditUserModalEditTitle") }}</button>
                    </div>
                </form>
            </div>
        </div>
    </div>
</template>

<script>
import { ref, computed } from "vue";
import { useI18n } from "vue-i18n";
// Import the stores
import { useAuthStore } from "@/stores/authStore";
// Import Notivue push
import { push } from "notivue";
// Importing the services
import { users } from "@/services/usersService";
// Import units utils
import { cmToFeetInches, feetAndInchesToCm } from "@/utils/unitsUtils";

export default {
    props: {
		action: {
			type: String,
			required: true,
		},
		user: {
			type: Object,
			required: false,
		},
	},
    emits: ["userPhotoDeleted", "isLoadingNewUser", "createdUser", "editedUser"],
    setup(props, { emit }) {
		const authStore = useAuthStore();
		const { t, locale } = useI18n();
        // edit user specific variables
		const editUserId = ref("");
        // edit and add user variables
        const newEditUserPhotoFile = ref(null);
		const newEditUserUsername = ref("");
		const newEditUserName = ref("");
		const newEditUserEmail = ref("");
		const newEditUserCity = ref(null);
		const newEditUserBirthDate = ref(null);
		const newEditUserGender = ref(1);
		const newEditUserUnits = ref(1);
		const newEditUserHeightCms = ref(null);
        const newEditUserHeightFeet = ref(null);
        const newEditUserHeightInches = ref(null);
        const isFeetValid = computed(() => {
            return newEditUserHeightFeet.value >= 0 && newEditUserHeightFeet.value <= 10;
        });
        const isInchesValid = computed(() => {
            return newEditUserHeightInches.value >= 0 && newEditUserHeightInches.value <= 11;
        });
		const newEditUserPreferredLanguage = ref("us");
		const newEditUserAccessType = ref(1);
        const newEditUserIsActive = ref(1);
        const newEditUserPhotoPath = ref(null);
		// new user variables
		const newUserPassword = ref("");
		const isPasswordValid = computed(() => {
			const regex =
				/^(?=.*[A-Z])(?=.*\d)(?=.*[ !\"#$%&'()*+,\-./:;<=>?@[\\\]^_`{|}~])[A-Za-z\d !"#$%&'()*+,\-./:;<=>?@[\\\]^_`{|}~]{8,}$/;
			return regex.test(newUserPassword.value);
		});

        if (props.user) {
			editUserId.value = `editUserModal${props.user.id}`;
			newEditUserUsername.value = props.user.username;
            newEditUserName.value = props.user.name;
            newEditUserEmail.value = props.user.email;
            newEditUserCity.value = props.user.city;
            newEditUserBirthDate.value = props.user.birthdate;
            newEditUserGender.value = props.user.gender;
            newEditUserUnits.value = props.user.units;
            newEditUserHeightCms.value = props.user.height;
            newEditUserPreferredLanguage.value = props.user.preferred_language;
            newEditUserAccessType.value = props.user.access_type;
            newEditUserIsActive.value = props.user.is_active;
            newEditUserPhotoPath.value = props.user.photo_path;
            if (props.user.height) {
                const { feet, inches } = cmToFeetInches(props.user.height);
                newEditUserHeightFeet.value = feet;
                newEditUserHeightInches.value = inches;
            }
		}

        async function handleFileChange(event) {
			newEditUserPhotoFile.value = event.target.files?.[0] ?? null;
		}

        async function submitDeleteUserPhoto() {
			try {
				await users.deleteUserPhoto(props.user.id);
                
                emit("userPhotoDeleted", props.user.id);

				// Set the success message and show the success alert.
				push.success(t("usersListComponent.userPhotoDeleteSuccessMessage"));
			} catch (error) {
				// Set the error message
				push.error(
					`${t("usersListComponent.userPhotoDeleteErrorMessage")} - ${error}`,
				);
			}
		}

        async function submitAddUserForm() {
			// Set the loading variable to true.
			emit("isLoadingNewUser", true);
			try {
				if (isPasswordValid.value) {
					// Create the gear data object
					const data = {
						name: newEditUserName.value,
						username: newEditUserUsername.value,
						email: newEditUserEmail.value,
						city: newEditUserCity.value,
						birthdate: newEditUserBirthDate.value,
						preferred_language: newEditUserPreferredLanguage.value,
						gender: newEditUserGender.value,
						units: newEditUserUnits.value,
						height: newEditUserHeightCms.value,
						access_type: newEditUserAccessType.value,
						photo_path: null,
						is_active: newEditUserIsActive.value,
						password: newUserPassword.value,
					};

					// Create the user and get the created user
					const createdUser = await users.createUser(data);

					// If there is a photo, upload it and get the photo url.
					if (newEditUserPhotoFile.value) {
						try {
							createdUser.photo_path = await users.uploadImage(newEditUserPhotoFile.value, createdUser.id);
						} catch (error) {
							// Set the error message
							push.error(`${t("generalItems.errorFetchingInfo")} - ${error}`);
						}
					}

                    // Set the loading variable to false.
					emit("isLoadingNewUser", false);

                    // Get the created user and add it to the array.
                    emit("createdUser", createdUser);

					// Set the success message and show the success alert.
					push.success(t("settingsUsersZone.successUserAdded"));
				}
			} catch (error) {
				// If there is an error, set the error message and show the error alert.
				push.error(`${t("generalItems.errorFetchingInfo")} - ${error}`);
			} finally {
				// Set the loading variable to false.
				emit("isLoadingNewUser", false);
			}
		}

        async function submitEditUserForm() {
			try {
				const data = {
					id: props.user.id,
					username: newEditUserUsername.value,
					name: newEditUserName.value,
					email: newEditUserEmail.value,
					city: newEditUserCity.value,
					birthdate: newEditUserBirthDate.value,
					gender: newEditUserGender.value,
					units: newEditUserUnits.value,
					height: newEditUserHeightCms.value,
					preferred_language: newEditUserPreferredLanguage.value,
					access_type: newEditUserAccessType.value,
					photo_path: newEditUserPhotoPath.value,
					is_active: newEditUserIsActive.value,
				};

				await users.editUser(data.id, data);

				// If there is a photo, upload it and get the photo url.
				if (newEditUserPhotoFile.value) {
					try {
						data.photo_path = await users.uploadImage(
							newEditUserPhotoFile.value,
							data.id,
						);
					} catch (error) {
						// Set the error message
						push.error(`${t("generalItems.errorFetchingInfo")} - ${error}`);
					}
				}

                emit("editedUser", data);

                if (data.id === authStore.user.id) {
                    authStore.setUser(data, authStore.session_id, locale);
                }

				// Set the success message and show the success alert.
				push.success(t("usersListComponent.userEditSuccessMessage"));
			} catch (error) {
				// If there is an error, set the error message and show the error alert.
				push.error(
					`${t("usersListComponent.userEditErrorMessage")} - ${error}`,
				);
			}
		}

        function handleSubmit() {
            if (authStore.user.units === 1) {
                if (newEditUserHeightCms.value !== props.user.height) {
                    const { feet, inches } = cmToFeetInches(newEditUserHeightCms.value);
                    newEditUserHeightFeet.value = feet;
                    newEditUserHeightInches.value = inches;
                }
            } else {
                const { feet, inches } = cmToFeetInches(props.user.height);
                if (feet !== newEditUserHeightFeet.value || inches !== newEditUserHeightInches.value) {
                    newEditUserHeightCms.value = feetAndInchesToCm(newEditUserHeightFeet.value, newEditUserHeightInches.value);
                }
            }
            
            if (props.action === 'add') {
                submitAddUserForm();
            } else {
                submitEditUserForm();
            }
        }

        return {
            authStore,
			t,
            editUserId,
            newEditUserPhotoFile,
            newEditUserUsername,
            newEditUserName,
            newEditUserEmail,
            newEditUserCity,
            newEditUserBirthDate,
            newEditUserGender,
            newEditUserUnits,
            newEditUserHeightCms,
            newEditUserHeightFeet,
            newEditUserHeightInches,
            newEditUserPreferredLanguage,
            newEditUserAccessType,
            newEditUserIsActive,
            newEditUserPhotoPath,
            newUserPassword,
            isPasswordValid,
            isFeetValid,
            isInchesValid,
            submitDeleteUserPhoto,
            handleFileChange,
            handleSubmit,
		};
    },
};
</script>