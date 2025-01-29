<template>
    <div class="col">
        <div class="row row-gap-3">
            <div class="col-lg-4 col-md-12">
                <div class="justify-content-center align-items-center d-flex">
                    <UserAvatarComponent :user="authStore.user" :width=180 :height=180 />
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
                <UsersAddEditUserModalComponent :action="'profile'" :user="authStore.user"/>
            </div>
            <div class="col">
                <!-- user name -->
                <h2>{{ authStore.user.name }}</h2>
                <!-- user username -->
                <p><b>{{ $t("usersAddEditUserModalComponent.addEditUserModalUsernameLabel") }}: </b>{{ authStore.user.username }}</p>
                <!-- user email -->
                <p><b>{{ $t("usersAddEditUserModalComponent.addEditUserModalEmailLabel") }}: </b>{{ authStore.user.email }}</p>
                <!-- user city -->
                <p>
                    <b>{{ $t("usersAddEditUserModalComponent.addEditUserModalCityLabel") }}: </b>
                    <span v-if="authStore.user.city">{{ authStore.user.city }}</span>
                    <span v-else>N/A</span>
                </p>
                <!-- user birthdate -->
                <p>
                    <b>{{ $t("usersAddEditUserModalComponent.addEditUserModalBirthdayLabel") }}: </b>
                    <span v-if="authStore.user.birthdate">{{ authStore.user.birthdate }}</span>
                    <span v-else>N/A</span>
                </p>
                <!-- user gender -->
                <p>
                    <b>{{ $t("usersAddEditUserModalComponent.addEditUserModalGenderLabel") }}: </b>
                    <span v-if="authStore.user.gender == 1">{{ $t("usersAddEditUserModalComponent.addEditUserModalGenderOption1") }}</span>
                    <span v-else>{{ $t("usersAddEditUserModalComponent.addEditUserModalGenderOption2") }}</span>
                </p>
                <!-- user units -->
                <p>
                    <b>{{ $t("usersAddEditUserModalComponent.addEditUserModalUnitsLabel") }}: </b>
                    <span v-if="authStore.user.units == 1">{{ $t("usersAddEditUserModalComponent.addEditUserModalUnitsOption1") }}</span>
                    <span v-else>{{ $t("usersAddEditUserModalComponent.addEditUserModalUnitsOption2") }}</span>
                </p>
                <!-- user height -->
                <p>
                    <b>{{ $t("usersAddEditUserModalComponent.addEditUserModalHeightLabel") }} 
                        <span v-if="authStore.user.units == 1">({{ $t("generalItems.unitsCm") }}): </span>
                        <span v-else>({{ $t("generalItems.unitsFeetInches") }}): </span>
                    </b>
                    <span v-if="authStore.user.height">
                        <span v-if="authStore.user.units == 1">{{ authStore.user.height }}{{ $t("generalItems.unitsCm") }}</span>
                        <span v-else>{{ feet }}’{{ inches }}’’</span>
                    </span>
                    <span v-else>N/A</span>
                </p>
                <!-- user preferred language -->
                <p>
                    <b>{{ $t("usersAddEditUserModalComponent.addEditUserModalUserPreferredLanguageLabel") }}: </b>
                    <span v-if="authStore.user.preferred_language == 'us'">{{ $t("usersAddEditUserModalComponent.addEditUserModalPreferredLanguageOption1") }}</span>
                    <span v-if="authStore.user.preferred_language == 'ca'">{{ $t("usersAddEditUserModalComponent.addEditUserModalPreferredLanguageOption2") }}</span>
                    <span v-if="authStore.user.preferred_language == 'pt'">{{ $t("usersAddEditUserModalComponent.addEditUserModalPreferredLanguageOption3") }}</span>
                    <span v-if="authStore.user.preferred_language == 'de'">{{ $t("usersAddEditUserModalComponent.addEditUserModalPreferredLanguageOption4") }}</span>
                    <span v-if="authStore.user.preferred_language == 'fr'">{{ $t("usersAddEditUserModalComponent.addEditUserModalPreferredLanguageOption5") }}</span>
                </p>
                <!-- user type -->
                <p>
                    <b>{{ $t("usersAddEditUserModalComponent.addEditUserModalUserTypeLabel") }}: </b>
                    <span v-if="authStore.user.access_type == 1">{{ $t("usersAddEditUserModalComponent.addEditUserModalUserTypeOption1") }}</span>
                    <span v-else>{{ $t("usersAddEditUserModalComponent.addEditUserModalUserTypeOption2") }}</span>
                </p>
            </div>
        </div>
    </div>
</template>

<script>
import { useI18n } from "vue-i18n";
// Importing the services
import { profile } from "@/services/profileService";
// Import the stores
import { useAuthStore } from "@/stores/authStore";
// Import Notivue push
import { push } from "notivue";
// Import units utils
import { cmToFeetInches } from "@/utils/unitsUtils";
// Importing the components
import UserAvatarComponent from "../Users/UserAvatarComponent.vue";
import UsersAddEditUserModalComponent from "@/components/Settings/SettingsUsersZone/UsersAddEditUserModalComponent.vue";

export default {
	components: {
		UserAvatarComponent,
		UsersAddEditUserModalComponent,
	},
	setup() {
		const authStore = useAuthStore();
		const { t, locale } = useI18n();
        const { feet, inches } = cmToFeetInches(authStore.user.height);

		async function submitDeleteUserPhoto() {
			try {
				// Delete the user photo from the server
				await profile.deleteProfilePhoto();

				// Update the user photo
				const user = authStore.user;
				user.photo_path = null;

				// Save the user data in the local storage and in the store.
				authStore.setUser(user, authStore.session_id, locale);

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
			submitDeleteUserPhoto,
            feet,
            inches,
		};
	},
};
</script>