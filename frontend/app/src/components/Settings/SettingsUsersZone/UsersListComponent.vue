<template>
    <li class="list-group-item rounded" :class="{ 'shadow my-1': userDetails }">
		<div class="d-flex justify-content-between">
			<div class="d-flex align-items-center">
				<UserAvatarComponent :user="user" :width=55 :height=55 />
				<div class="ms-3">
					<div class="fw-bold">
						{{ user.username }}
					</div>
					<b>{{ $t("usersListComponent.userListAccessTypeLabel") }}</b>
					<span v-if="user.access_type == 1">{{ $t("usersListComponent.userListAccessTypeOption1") }}</span>
					<span v-else>{{ $t("usersListComponent.userListAccessTypeOption2") }}</span>
				</div>
			</div>
			<div>
				<span class="badge bg-secondary-subtle border border-secondary-subtle text-secondary-emphasis align-middle me-2" v-if="user.id == authStore.user.id">{{ $t("usersListComponent.userListUserIsMeBadge") }}</span>
				<span class="badge bg-warning-subtle border border-warning-subtle text-warning-emphasis align-middle me-2" v-if="user.access_type == 2">{{ $t("usersListComponent.userListUserIsAdminBadge") }}</span>
				<span class="badge bg-success-subtle border border-success-subtle text-success-emphasis align-middle" v-if="user.is_active == 1">{{ $t("usersListComponent.userListUserIsActiveBadge") }}</span>
				<span class="badge bg-danger-subtle border border-danger-subtle text-danger-emphasis align-middle" v-else>{{ $t("usersListComponent.userListUserIsInactiveBadge") }}</span>

				<!-- change user password button -->
				<a class="btn btn-link btn-lg link-body-emphasis" href="#" role="button" data-bs-toggle="modal" :data-bs-target="`#editUserPasswordModal${user.id}`"><font-awesome-icon :icon="['fas', 'fa-key']" /></a>

				<!-- change user password Modal -->
				<div class="modal fade" :id="`editUserPasswordModal${user.id}`" tabindex="-1" :aria-labelledby="`editUserPasswordModal${user.id}`" aria-hidden="true">
					<div class="modal-dialog">
						<div class="modal-content">
							<div class="modal-header">
								<h1 class="modal-title fs-5" :id="`editUserPasswordModal${user.id}`">{{ $t("usersListComponent.modalChangeUserPasswordTitle") }}</h1>
								<button type="button" class="btn-close" data-bs-dismiss="modal" aria-label="Close"></button>
							</div>
							<form @submit.prevent="submitChangeUserPasswordForm">
								<div class="modal-body">
									<SettingsPasswordRequirementsComponent />

									<p>{{ $t("usersListComponent.modalChangeUserPasswordBodyLabel") }}<b>{{ user.username }}</b></p>

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
				<a class="btn btn-link btn-lg link-body-emphasis" href="#" role="button" data-bs-toggle="modal" :data-bs-target="`#editUserModal${user.id}`"><font-awesome-icon :icon="['fas', 'fa-pen-to-square']" /></a>

				<!-- Modal edit user -->
				<div class="modal fade" :id="`editUserModal${user.id}`" tabindex="-1" :aria-labelledby="`editUserModal${user.id}`" aria-hidden="true">
					<div class="modal-dialog">
						<div class="modal-content">
							<div class="modal-header">
								<h1 class="modal-title fs-5" :id="`editUserModal${user.id}`">{{ $t("usersListComponent.modalEditUserTitle") }}</h1>
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
											<div class="col" v-if="user.photo_path">
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
									<!-- units fields -->
									<label for="userUnitsEdit"><b>* {{ $t("settingsUsersZone.addUserModalUnitsLabel") }}</b></label>
									<select class="form-control" name="userUnitsEdit" v-model="editUserUnits" required>
										<option value="1">{{ $t("settingsUsersZone.addUserModalUnitsOption1") }}</option>
										<option value="2">{{ $t("settingsUsersZone.addUserModalUnitsOption2") }}</option>
									</select>
									<!-- height fields -->
									<label for="userHeightEdit"><b>{{ $t("settingsUsersZone.addUserModalHeightLabel") }} (cm)</b></label>
									<input class="form-control" type="number" name="userHeightEdit" :placeholder='$t("settingsUsersZone.addUserModalHeightPlaceholder") + " (cm)"' v-model="editUserHeight">
									<!-- preferred language fields -->
									<label for="userPreferredLanguageEdit"><b>* {{ $t("settingsUsersZone.addUserModalUserPreferredLanguageLabel") }}</b></label>
									<select class="form-control" name="userPreferredLanguageEdit" v-model="editUserPreferredLanguage" required>
										<option value="us">{{ $t("settingsUsersZone.addUserModalPreferredLanguageOption1") }}</option>
										<option value="ca">{{ $t("settingsUsersZone.addUserModalPreferredLanguageOption2") }}</option>
										<option value="pt">{{ $t("settingsUsersZone.addUserModalPreferredLanguageOption3") }}</option>
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
				<a class="btn btn-link btn-lg link-body-emphasis" href="#" role="button" data-bs-toggle="modal" :data-bs-target="`#deleteUserModal${user.id}`" v-if="authStore.user.id != user.id"><font-awesome-icon :icon="['fas', 'fa-trash-can']" /></a>

				<!-- delete user modal -->
				<ModalComponent :modalId="`deleteUserModal${user.id}`" :title="t('usersListComponent.modalDeleteUserTitle')" :body="`${t('usersListComponent.modalDeleteUserBody')}<b>${user.username}</b>?`" :actionButtonType="`danger`" :actionButtonText="t('usersListComponent.modalDeleteUserTitle')" @submitAction="submitDeleteUser"/>

				<!-- button toggle user details -->
				<a class="btn btn-link btn-lg link-body-emphasis" data-bs-toggle="collapse" :href="`#collapseUserDetails${user.id}`" role="button" aria-expanded="false" @click="showUserDetails()" aria-controls="`collapseUserDetails${user.id}`">
					<font-awesome-icon :icon="['fas', 'caret-down']" v-if="!userDetails"/>
					<font-awesome-icon :icon="['fas', 'caret-up']" v-else/>
				</a>
			</div>
		</div>
		<div class="collapse" :id="`collapseUserDetails${user.id}`">
			<br>
			<h6>{{ $t("usersListComponent.userListUserSessionsTitle") }}</h6>
			<div v-if="isLoading">
				<LoadingComponent />
			</div>
			<div v-else-if="userSessions && userSessions.length > 0">
				<UserSessionsListComponent v-for="session in userSessions" :key="session.id" :session="session" @sessionDeleted="updateSessionListDeleted"/>
			</div>
			<div v-else>
				<NoItemsFoundComponents />
			</div>
		</div>
    </li>
</template>

<script>
import { ref, computed, onMounted } from "vue";
import { useI18n } from "vue-i18n";
// Importing the services
import { users } from "@/services/usersService";
// Import the stores
import { useAuthStore } from "@/stores/authStore";
// Import Notivue push
import { push } from "notivue";
// Import services
import { session } from "@/services/sessionService";
// Importing the components
import SettingsPasswordRequirementsComponent from "@/components/Settings/SettingsPasswordRequirementsComponent.vue";
import UserAvatarComponent from "@/components/Users/UserAvatarComponent.vue";
import UserSessionsListComponent from "@/components/Settings/SettingsUserSessionsZone/UserSessionsListComponent.vue";
import NoItemsFoundComponents from "@/components/GeneralComponents/NoItemsFoundComponents.vue";
import LoadingComponent from "@/components/GeneralComponents/LoadingComponent.vue";
import ModalComponent from "@/components/Modals/ModalComponent.vue";

export default {
	components: {
		SettingsPasswordRequirementsComponent,
		UserAvatarComponent,
		LoadingComponent,
		NoItemsFoundComponents,
		UserSessionsListComponent,
		ModalComponent,
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
		const editUserUnits = ref(userProp.value.units);
		const editUserHeight = ref(userProp.value.height);
		const editUserPreferredLanguage = ref(userProp.value.preferred_language);
		const editUserAccessType = ref(userProp.value.access_type);
		const editUserIsActive = ref(userProp.value.is_active);
		const userDetails = ref(false);
		const userSessions = ref([]);
		const isLoading = ref(true);

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
					units: editUserUnits.value,
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
				userProp.value.units = editUserUnits.value;
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

		function showUserDetails() {
			userDetails.value = !userDetails.value;
		}

		async function updateSessionListDeleted(sessionDeletedId) {
			try {
				// Delete session in the DB
				await session.deleteSession(sessionDeletedId, props.user.id);

				// Remove the session from the userSessions
				userSessions.value = userSessions.value.filter(
					(session) => session.id !== sessionDeletedId,
				);

				// Show the success alert.
				push.success(
					t("settingsSecurityZone.successDeleteSession"),
				);
			} catch (error) {
				// If there is an error, show the error alert.
				push.error(
					`${t("settingsSecurityZone.errorDeleteSession")} - ${error}`,
				);
			}
		}

		onMounted(async () => {
			// Fetch the user sessions
			userSessions.value = await session.getUserSessions(props.user.id);

			// Set the isLoading to false
			isLoading.value = false;
		});

		return {
			t,
			authStore,
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
			editUserUnits,
			editUserHeight,
			editUserPreferredLanguage,
			editUserAccessType,
			editUserIsActive,
			submitEditUserForm,
			handleFileChange,
			submitDeleteUser,
			submitDeleteUserPhoto,
			showUserDetails,
			userDetails,
			userSessions,
			isLoading,
			updateSessionListDeleted,
		};
	},
};
</script>