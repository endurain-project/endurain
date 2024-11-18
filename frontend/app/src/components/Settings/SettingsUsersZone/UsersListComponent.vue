<template>
    <li class="list-group-item d-flex justify-content-between">
        <div class="d-flex align-items-center">
            <UserAvatarComponent :userProp="userProp" :width=55 :height=55 />
            <div class="ms-3">
                <div class="fw-bold">
                    {{ userProp.username }}
                </div>
                <b>{{ $t("usersListComponent.userListAccessTypeLabel") }}</b>
                <span v-if="userProp.access_type == 1">{{ $t("usersListComponent.userListAccessTypeOption1") }}</span>
                <span v-else>{{ $t("usersListComponent.userListAccessTypeOption2") }}</span>
            </div>
        </div>
        <div>
            <span class="badge bg-secondary-subtle border border-secondary-subtle text-secondary-emphasis align-middle me-2" v-if="user.id == authStore.user.id">{{ $t("usersListComponent.userListUserIsMeBadge") }}</span>
            <span class="badge bg-warning-subtle border border-warning-subtle text-warning-emphasis align-middle me-2" v-if="user.access_type == 2">{{ $t("usersListComponent.userListUserIsAdminBadge") }}</span>
            <span class="badge bg-success-subtle border border-success-subtle text-success-emphasis align-middle" v-if="user.is_active == 1">{{ $t("usersListComponent.userListUserIsActiveBadge") }}</span>
            <span class="badge bg-danger-subtle border border-danger-subtle text-danger-emphasis align-middle" v-else>{{ $t("usersListComponent.userListUserIsInactiveBadge") }}</span>

            <!-- change user password button -->
            <a class="btn btn-link btn-lg link-body-emphasis" href="#" role="button" data-bs-toggle="modal" :data-bs-target="`#editUserPasswordModal${userProp.id}`"><font-awesome-icon :icon="['fas', 'fa-key']" /></a>

            <!-- change user password Modal -->
            <div class="modal fade" :id="`editUserPasswordModal${userProp.id}`" tabindex="-1" :aria-labelledby="`editUserPasswordModal${userProp.id}`" aria-hidden="true">
                <div class="modal-dialog">
                    <div class="modal-content">
                        <div class="modal-header">
                            <h1 class="modal-title fs-5" :id="`editUserPasswordModal${userProp.id}`">{{ $t("usersListComponent.modalChangeUserPasswordTitle") }}</h1>
                            <button type="button" class="btn-close" data-bs-dismiss="modal" aria-label="Close"></button>
                        </div>
                        <form @submit.prevent="submitChangeUserPasswordForm">
                            <div class="modal-body">
                                <SettingsPasswordRequirementsComponent />

                                <p>{{ $t("usersListComponent.modalChangeUserPasswordBodyLabel") }}<b>{{ userProp.username }}</b></p>

                                <!-- password fields -->
                                <label for="validationNewPassword"><b>* {{ $t("usersListComponent.modalChangeUserPasswordPasswordLabel") }}</b></label>
                                <input class="form-control" :class="{ 'is-invalid': !isNewPasswordValid || !isPasswordMatch }" type="password" id="validationNewPassword" aria-describedby="validationNewPasswordFeedback" :placeholder='$t("usersListComponent.modalChangeUserPasswordPasswordLabel")' v-model="newPassword" required>
                                <div id="validationNewPasswordFeedback" class="invalid-feedback" v-if="!isNewPasswordValid">
                                    {{ $t("usersListComponent.modalChangeUserPasswordFeedbackLabel") }}
                                </div>
                                <div id="validationNewPasswordFeedback" class="invalid-feedback" v-if="!isPasswordMatch">
                                    {{ $t("usersListComponent.modalChangeUserPasswordPasswordsDoNotMatchFeedbackLabel") }}
                                </div>
                                <!-- repeat password fields -->

                                <label class="mt-1" for="validationNewPasswordRepeat"><b>* {{ $t("usersListComponent.modalChangeUserPasswordPasswordConfirmationLabel") }}</b></label>
                                <input class="form-control" :class="{ 'is-invalid': !isNewPasswordRepeatValid || !isPasswordMatch }" type="password" id="validationNewPasswordRepeat" aria-describedby="validationNewPasswordRepeatFeedback" :placeholder='$t("usersListComponent.modalChangeUserPasswordPasswordConfirmationLabel")' v-model="newPasswordRepeat" required>
                                <div id="validationNewPasswordRepeatFeedback" class="invalid-feedback" v-if="!isNewPasswordRepeatValid">
                                    {{ $t("usersListComponent.modalChangeUserPasswordFeedbackLabel") }}
                                </div>
                                <div id="validationNewPasswordRepeatFeedback" class="invalid-feedback" v-if="!isPasswordMatch">
                                    {{ $t("usersListComponent.modalChangeUserPasswordPasswordsDoNotMatchFeedbackLabel") }}
                                </div>

                                <p>* {{ $t("generalItems.requiredField") }}</p>
                            </div>
                            <div class="modal-footer">
                                <button type="button" class="btn btn-secondary" data-bs-dismiss="modal">{{ $t("generalItems.buttonClose") }}</button>
                                <button type="submit" class="btn btn-success" :disabled="!isNewPasswordValid || !isNewPasswordRepeatValid || !isPasswordMatch" name="editUserPasswordAdmin" data-bs-dismiss="modal">{{ $t("usersListComponent.modalChangeUserPasswordTitle") }}</button>
                            </div>
                        </form>
                    </div>
                </div>
            </div>

            <!-- edit user button -->
            <a class="btn btn-link btn-lg link-body-emphasis" href="#" role="button" data-bs-toggle="modal" :data-bs-target="`#editUserModal${userProp.id}`"><font-awesome-icon :icon="['fas', 'fa-pen-to-square']" /></a>

            <!-- Modal edit user -->
            <div class="modal fade" :id="`editUserModal${userProp.id}`" tabindex="-1" :aria-labelledby="`editUserModal${userProp.id}`" aria-hidden="true">
                <div class="modal-dialog">
                    <div class="modal-content">
                        <div class="modal-header">
                            <h1 class="modal-title fs-5" :id="`editUserModal${userProp.id}`">{{ $t("usersListComponent.modalEditUserTitle") }}</h1>
                            <button type="button" class="btn-close" data-bs-dismiss="modal" aria-label="Close"></button>
                        </div>
                        <form @submit.prevent="submitEditUserForm">
                            <div class="modal-body">
                                <label for="userImgEdit"><b>{{ $t("settingsUsersZone.addUserModalUserPhotoLabel") }}</b></label>
                                <div>
                                    <div class="row">
                                        <div class="col">
                                            <input class="form-control" type="file" accept="image/*" name="userImgEdit" id="userImgEdit" @change="handleFileChange">
                                        </div>
                                        <div class="col" v-if="userProp.photo_path">
                                            <a class="w-100 btn btn-danger" @click="submitDeleteUserPhoto" data-bs-dismiss="modal">{{ $t("usersListComponent.modalEditUserDeleteUserPhotoButton") }}</a>
                                        </div>
                                    </div>
                                </div>
                                <!-- username fields -->
                                <label for="userUsernameEdit"><b>* {{ $t("settingsUsersZone.addUserModalUsernameLabel") }}</b></label>
                                <input class="form-control" type="text" name="userUsernameEdit" :placeholder='$t("settingsUsersZone.addUserModalUsernamePlaceholder")' maxlength="250" v-model="editUserUsername" required>
                                <!-- name fields -->
                                <label for="userNameEdit"><b>* {{ $t("settingsUsersZone.addUserModalNameLabel") }}</b></label>
                                <input class="form-control" type="text" name="userNameEdit" :placeholder='$t("settingsUsersZone.addUserModalNamePlaceholder")' maxlength="250" v-model="editUserName" required>
                                <!-- email fields -->
                                <label for="userEmailEdit"><b>* {{ $t("settingsUsersZone.addUserModalEmailLabel") }}</b></label>
                                <input class="form-control" type="text" name="userEmailEdit" :placeholder='$t("settingsUsersZone.addUserModalEmailPlaceholder")' maxlength="45" v-model="editUserEmail" required>
                                <!-- city fields -->
                                <label for="userCityEdit"><b>{{ $t("settingsUsersZone.addUserModalTownLabel") }}</b></label>
                                <input class="form-control" type="text" name="userCityEdit" :placeholder='$t("settingsUsersZone.addUserModalTownPlaceholder")' maxlength="45" v-model="editUserTown">
                                <!-- birth date fields -->
                                <label for="userBirthDateEdit"><b>{{ $t("settingsUsersZone.addUserModalBirthdayLabel") }}</b></label>
                                <input class="form-control" type="date" name="userBirthDateEdit" v-model="editUserBirthdate">
                                <!-- gender fields -->
                                <label for="userGenderEdit"><b>* {{ $t("settingsUsersZone.addUserModalGenderLabel") }}</b></label>
                                <select class="form-control" name="userGenderEdit" v-model="editUserGender" required>
                                    <option value="1">{{ $t("settingsUsersZone.addUserModalGenderOption1") }}</option>
                                    <option value="2">{{ $t("settingsUsersZone.addUserModalGenderOption2") }}</option>
								</select>
								<!-- height fields -->
								<label for="userHeightEdit"><b>{{ $t("settingsUsersZone.addUserModalHeightLabel") }}</b></label>
								<input class="form-control" type="number" name="userHeightEdit" :placeholder='$t("settingsUsersZone.addUserModalHeightPlaceholder")' v-model="editUserHeight">
                                <!-- preferred language fields -->
                                <label for="userPreferredLanguageEdit"><b>* {{ $t("settingsUsersZone.addUserModalUserPreferedLanguageLabel") }}</b></label>
                                <select class="form-control" name="userPreferredLanguageEdit" v-model="editUserPreferredLanguage" required>
                                    <option value="us">{{ $t("settingsUsersZone.addUserModalPreferredLanguageOption1") }}</option>
                                </select>
                                <!-- access type fields -->
                                <label for="userTypeEdit"><b>* {{ $t("settingsUsersZone.addUserModalUserTypeLabel") }}</b></label>
                                <select class="form-control" name="userTypeEdit" v-model="editUserAccessType" required>
                                    <option value="1">{{ $t("settingsUsersZone.addUserModalUserTypeOption1") }}</option>
                                    <option value="2">{{ $t("settingsUsersZone.addUserModalUserTypeOption2") }}</option>
                                </select>
                                <!-- user is_active fields -->
                                <label for="userIsActiveEdit"><b>* {{ $t("usersListComponent.modalEditUserIsUserActiveLabel") }}</b></label>
                                <select class="form-control" name="userIsActiveEdit" v-model="editUserIsActive" required>
                                    <option value="1">{{ $t("usersListComponent.modalEditUserIsUserActiveOption1") }}</option>
                                    <option value="2">{{ $t("usersListComponent.modalEditUserIsUserActiveOption2") }}</option>
                                </select>
                                <p>* {{ $t("generalItems.requiredField") }}</p>
                            </div>
                            <div class="modal-footer">
                                <button type="button" class="btn btn-secondary" data-bs-dismiss="modal">{{ $t("generalItems.buttonClose") }}</button>
                                <button type="submit" class="btn btn-success" name="userEdit" data-bs-dismiss="modal">{{ $t("usersListComponent.modalEditUserTitle") }}</button>
                            </div>
                        </form>
                    </div>
                </div>
            </div>

            <!-- delete user button -->
            <a class="btn btn-link btn-lg link-body-emphasis" href="#" role="button" data-bs-toggle="modal" :data-bs-target="`#deleteUserModal${userProp.id}`" v-if="authStore.user.id != userProp.id"><font-awesome-icon :icon="['fas', 'fa-trash-can']" /></a>

            <!-- delete user modal -->
            <div class="modal fade" :id="`deleteUserModal${userProp.id}`" tabindex="-1" :aria-labelledby="`deleteUserModal${userProp.id}`" aria-hidden="true">
                <div class="modal-dialog">
                    <div class="modal-content">
                        <div class="modal-header">
                            <h1 class="modal-title fs-5" :id="`deleteUserModal${userProp.id}`">{{ $t("usersListComponent.modalDeleteUserTitle") }}</h1>
                            <button type="button" class="btn-close" data-bs-dismiss="modal" aria-label="Close"></button>
                        </div>
                        <div class="modal-body">
                            <span>{{ $t("usersListComponent.modalDeleteUserBody") }}<b>{{ userProp.username }}</b>?</span>
                        </div>
                        <div class="modal-footer">
                            <button type="button" class="btn btn-secondary" data-bs-dismiss="modal">{{ $t("generalItems.buttonClose") }}</button>
                            <a type="button" @click="submitDeleteUser" class="btn btn-danger" data-bs-dismiss="modal">{{ $t("usersListComponent.modalDeleteUserTitle") }}</a>
                        </div>
                    </div>
                </div>
            </div>
        </div>
    </li>
</template>

<script>
import { ref, computed } from "vue";
import { useI18n } from "vue-i18n";
// Importing the services
import { users } from "@/services/usersService";
// Import the stores
import { useAuthStore } from "@/stores/authStore";
// Import Notivue push
import { push } from "notivue";
// Importing the components
import SettingsPasswordRequirementsComponent from "@/components/Settings/SettingsPasswordRequirementsComponent.vue";
import UserAvatarComponent from "@/components/Users/UserAvatarComponent.vue";

export default {
	components: {
		SettingsPasswordRequirementsComponent,
		UserAvatarComponent,
	},
	props: {
		user: {
			type: Object,
			required: true,
		},
	},
	emits: ["userDeleted"],
	setup(props, { emit }) {
		const { t } = useI18n();
		const authStore = useAuthStore();
		const userProp = ref(props.user);
		const newPassword = ref("");
		const newPasswordRepeat = ref("");
		const regex =
			/^(?=.*[A-Z])(?=.*\d)(?=.*[ !\"#$%&'()*+,\-./:;<=>?@[\\\]^_`{|}~])[A-Za-z\d !"#$%&'()*+,\-./:;<=>?@[\\\]^_`{|}~]{8,}$/;
		const isNewPasswordValid = computed(() => {
			return regex.test(newPassword.value);
		});
		const isNewPasswordRepeatValid = computed(() => {
			return regex.test(newPasswordRepeat.value);
		});
		const isPasswordMatch = computed(
			() => newPassword.value === newPasswordRepeat.value,
		);
		const editUserPhotoFile = ref(null);
		const editUserUsername = ref(userProp.value.username);
		const editUserName = ref(userProp.value.name);
		const editUserEmail = ref(userProp.value.email);
		const editUserTown = ref(userProp.value.city);
		const editUserBirthdate = ref(userProp.value.birthdate);
		const editUserGender = ref(userProp.value.gender);
		const editUserHeight = ref(userProp.value.height);
		const editUserPreferredLanguage = ref(userProp.value.preferred_language);
		const editUserAccessType = ref(userProp.value.access_type);
		const editUserIsActive = ref(userProp.value.is_active);

		async function handleFileChange(event) {
			editUserPhotoFile.value = event.target.files?.[0] ?? null;
		}

		async function submitChangeUserPasswordForm() {
			try {
				if (
					isNewPasswordValid.value &&
					isNewPasswordRepeatValid.value &&
					isPasswordMatch.value
				) {
					const data = {
						password: newPassword.value,
					};
					await users.editUserPassword(userProp.value.id, data);
					// Set the success message and show the success alert.
					push.success(
						t("usersListComponent.userChangePasswordSuccessMessage"),
					);
				}
			} catch (error) {
				// If there is an error, set the error message and show the error alert.
				push.error(
					`${t("usersListComponent.userChangePasswordErrorMessage")} - ${error}`,
				);
			}
		}

		async function submitEditUserForm() {
			try {
				const data = {
					id: userProp.value.id,
					username: editUserUsername.value,
					name: editUserName.value,
					email: editUserEmail.value,
					city: editUserTown.value,
					birthdate: editUserBirthdate.value,
					gender: editUserGender.value,
					height: editUserHeight.value,
					preferred_language: editUserPreferredLanguage.value,
					access_type: editUserAccessType.value,
					photo_path: null,
					is_active: editUserIsActive.value,
				};

				await users.editUser(userProp.value.id, data);

				// If there is a photo, upload it and get the photo url.
				if (editUserPhotoFile.value) {
					try {
						userProp.value.photo_path = await users.uploadImage(
							editUserPhotoFile.value,
							userProp.value.id,
						);
					} catch (error) {
						// Set the error message
						push.error(`${t("generalItems.errorFetchingInfo")} - ${error}`);
					}
				}

				userProp.value.username = editUserUsername.value;
				userProp.value.name = editUserName.value;
				userProp.value.email = editUserEmail.value;
				userProp.value.city = editUserTown.value;
				userProp.value.birthdate = editUserBirthdate.value;
				userProp.value.city = editUserTown.value;
				userProp.value.birthdate = editUserBirthdate.value;
				userProp.value.gender = editUserGender.value;
				userProp.value.height = editUserHeight.value;
				userProp.value.preferred_language = editUserPreferredLanguage.value;
				userProp.value.access_type = editUserAccessType.value;
				userProp.value.is_active = editUserIsActive.value;

				// Set the success message and show the success alert.
				push.success(t("usersListComponent.userEditSuccessMessage"));
			} catch (error) {
				// If there is an error, set the error message and show the error alert.
				push.error(
					`${t("usersListComponent.userEditErrorMessage")} - ${error}`,
				);
			}
		}

		async function submitDeleteUser() {
			try {
				await users.deleteUser(userProp.value.id);

				emit("userDeleted", userProp.value.id);
			} catch (error) {
				// If there is an error, set the error message and show the error alert.
				push.error(
					`${t("usersListComponent.userDeleteErrorMessage")} - ${error}`,
				);
			}
		}

		async function submitDeleteUserPhoto() {
			try {
				await users.deleteUserPhoto(userProp.value.id);
				userProp.value.photo_path = null;

				// Set the success message and show the success alert.
				push.success(t("usersListComponent.userPhotoDeleteSuccessMessage"));
			} catch (error) {
				// Set the error message
				push.error(
					`${t("usersListComponent.userPhotoDeleteErrorMessage")} - ${error}`,
				);
			}
		}

		return {
			t,
			authStore,
			userProp,
			newPassword,
			newPasswordRepeat,
			isNewPasswordValid,
			isNewPasswordRepeatValid,
			isPasswordMatch,
			submitChangeUserPasswordForm,
			editUserUsername,
			editUserName,
			editUserEmail,
			editUserTown,
			editUserBirthdate,
			editUserGender,
			editUserHeight,
			editUserPreferredLanguage,
			editUserAccessType,
			editUserIsActive,
			submitEditUserForm,
			handleFileChange,
			submitDeleteUser,
			submitDeleteUserPhoto,
		};
	},
};
</script>