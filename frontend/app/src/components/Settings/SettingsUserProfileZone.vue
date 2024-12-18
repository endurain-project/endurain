<template>
    <div class="col">
        <div class="row row-gap-3">
            <div class="col-lg-4 col-md-12">
                <div class="justify-content-center align-items-center d-flex">
                    <UserAvatarComponent :userProp="authStore.user" :width=180 :height=180 />
                </div>

                <!-- Delete profile photo section -->
                <a class="mt-4 w-100 btn btn-danger" href="#" role="button" data-bs-toggle="modal" data-bs-target="#deleteProfilePhotoModal" v-if="authStore.user.photo_path">{{ $t("settingsUserProfileZone.buttonDeleteProfilePhoto") }}</a>

                <!-- Modal delete profile photo -->
                <div class="modal fade" id="deleteProfilePhotoModal" tabindex="-1" aria-labelledby="deleteProfilePhotoModal" aria-hidden="true">
                    <div class="modal-dialog">
                        <div class="modal-content">
                            <div class="modal-header">
                                <h1 class="modal-title fs-5" id="deleteProfilePhotoModal">{{ $t("settingsUserProfileZone.buttonDeleteProfilePhoto") }}</h1>
                                <button type="button" class="btn-close" data-bs-dismiss="modal" aria-label="Close"></button>
                            </div>
                            <div class="modal-body">
                                {{ $t("settingsUserProfileZone.modalDeleteProfilePhotoBody") }}
                            </div>
                            <div class="modal-footer">
                                <button type="button" class="btn btn-secondary" data-bs-dismiss="modal">{{ $t("generalItems.buttonClose") }}</button>
                                <a type="button" class="btn btn-danger" data-bs-dismiss="modal" @click="submitDeleteUserPhoto">{{ $t("settingsUserProfileZone.buttonDeleteProfilePhoto") }}</a>
                            </div>
                        </div>
                    </div>
                </div>

                <!-- Edit profile section -->
                <a class="mt-2 w-100 btn btn-primary" href="#" role="button" data-bs-toggle="modal" data-bs-target="#editProfileModal">{{ $t("settingsUserProfileZone.buttonEditProfile") }}</a>

                <!-- Modal edit user -->
                <div class="modal fade" id="editProfileModal" tabindex="-1" aria-labelledby="editProfileModal" aria-hidden="true">
                    <div class="modal-dialog">
                        <div class="modal-content">
                            <div class="modal-header">
                                <h1 class="modal-title fs-5" id="editProfileModal">{{ $t("usersListComponent.modalEditUserTitle") }}</h1>
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
                                            <div class="col" v-if="authStore.user.photo_path">
                                                <a class="w-100 btn btn-danger" data-bs-dismiss="modal" @click="submitDeleteUserPhoto">{{ $t("usersListComponent.modalEditUserDeleteUserPhotoButton") }}</a>
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
                                        <option value="ca">{{ $t("settingsUsersZone.addUserModalPreferredLanguageOption2") }}</option>
                                        <option value="pt">{{ $t("settingsUsersZone.addUserModalPreferredLanguageOption3") }}</option>
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
            </div>
            <div class="col">
                <!-- user name -->
                <h2>{{ authStore.user.name }}</h2>
                <!-- user username -->
                <p><b>{{ $t("settingsUsersZone.addUserModalUsernameLabel") }}: </b>{{ authStore.user.username }}</p>
                <!-- user email -->
                <p><b>{{ $t("settingsUsersZone.addUserModalEmailLabel") }}: </b>{{ authStore.user.email }}</p>
                <!-- user city -->
                <p>
                    <b>{{ $t("settingsUsersZone.addUserModalTownLabel") }}: </b>
                    <span v-if="authStore.user.city">{{ authStore.user.city }}</span>
                    <span v-else>N/A</span>
                </p>
                <!-- user birthdate -->
                <p>
                    <b>{{ $t("settingsUsersZone.addUserModalBirthdayLabel") }}: </b>
                    <span v-if="authStore.user.birthdate">{{ authStore.user.birthdate }}</span>
                    <span v-else>N/A</span>
                </p>
                <!-- user gender -->
                <p>
                    <b>{{ $t("settingsUsersZone.addUserModalGenderLabel") }}: </b>
                    <span v-if="authStore.user.gender == 1">{{ $t("settingsUsersZone.addUserModalGenderOption1") }}</span>
                    <span v-else>{{ $t("settingsUsersZone.addUserModalGenderOption2") }}</span>
                </p>
                <!-- user height -->
                <p>
                    <b>{{ $t("settingsUsersZone.addUserModalHeightLabel") }}: </b>
                    <span v-if="authStore.user.height">{{ authStore.user.height }}cm</span>
                    <span v-else>N/A</span>
                </p>
                <!-- user preferred language -->
                <p>
                    <b>{{ $t("settingsUsersZone.addUserModalUserPreferedLanguageLabel") }}: </b>
                    <span v-if="authStore.user.preferred_language == 'us'">{{ $t("settingsUsersZone.addUserModalPreferredLanguageOption1") }}</span>
                </p>
                <!-- user type -->
                <p>
                    <b>{{ $t("settingsUsersZone.addUserModalUserTypeLabel") }}: </b>
                    <span v-if="authStore.user.access_type == 1">{{ $t("settingsUsersZone.addUserModalUserTypeOption1") }}</span>
                    <span v-else>{{ $t("settingsUsersZone.addUserModalUserTypeOption2") }}</span>
                </p>
            </div>
        </div>
    </div>
</template>

<script>
import { ref } from "vue";
import { useI18n } from "vue-i18n";
// Importing the services
import { profile } from "@/services/profileService";
// Import the stores
import { useAuthStore } from "@/stores/authStore";
// Import Notivue push
import { push } from "notivue";
// Importing the components
import UserAvatarComponent from "../Users/UserAvatarComponent.vue";

export default {
	components: {
		UserAvatarComponent,
	},
	setup() {
		const authStore = useAuthStore();
		const { t, locale } = useI18n();
		const editUserPhotoFile = ref(null);
		const editUserUsername = ref(authStore.user.username);
		const editUserName = ref(authStore.user.name);
		const editUserEmail = ref(authStore.user.email);
		const editUserTown = ref(authStore.user.city);
		const editUserBirthdate = ref(authStore.user.birthdate);
		const editUserGender = ref(authStore.user.gender);
		const editUserHeight = ref(authStore.user.height);
		const editUserPreferredLanguage = ref(authStore.user.preferred_language);
		const editUserAccessType = ref(authStore.user.access_type);

		async function handleFileChange(event) {
			editUserPhotoFile.value = event.target.files?.[0] ?? null;
		}

		async function submitEditUserForm() {
			try {
                if (editUserHeight.value === "" || editUserHeight.value === 0) {
                    editUserHeight.value = null;
                }
				const data = {
					id: authStore.user.id,
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
					is_active: 1,
				};

				await profile.editProfile(data);

				// If there is a photo, upload it and get the photo url.
				if (editUserPhotoFile.value) {
					try {
						data.photo_path = await profile.uploadProfileImage(
							editUserPhotoFile.value,
						);
					} catch (error) {
						// Set the error message
						push.error(`${t("generalItems.errorFetchingInfo")} - ${error}`);
					}
				}

				// Save the user data in the local storage and in the store.
				authStore.setUser(data, locale);

				// Set the success message and show the success alert.
				push.success(t("usersListComponent.userEditSuccessMessage"));
			} catch (error) {
				// If there is an error, set the error message and show the error alert.
				push.error(
					`${t("usersListComponent.userEditErrorMessage")} - ${error}`,
				);
			}
		}

		async function submitDeleteUserPhoto() {
			try {
				// Delete the user photo from the server
				await profile.deleteProfilePhoto();

				// Update the user photo
				const user = authStore.user;
				user.photo_path = null;

				// Save the user data in the local storage and in the store.
				authStore.setUser(user, locale);

				// Set the success message and show the success alert.
				push.success(t("usersListComponent.userPhotoDeleteSuccessMessage"));
			} catch (error) {
				// Show the error message
				push.error(
					`${t("usersListComponent.userPhotoDeleteErrorMessage")} - ${error}`,
				);
			}
		}

		return {
			authStore,
			t,
			editUserUsername,
			editUserName,
			editUserEmail,
			editUserTown,
			editUserBirthdate,
			editUserGender,
			editUserHeight,
			editUserPreferredLanguage,
			editUserAccessType,
			submitEditUserForm,
			submitDeleteUserPhoto,
			handleFileChange,
		};
	},
};
</script>