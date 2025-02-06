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
                <ModalComponent modalId="deleteProfilePhotoModal" :title="t('settingsUserProfileZone.buttonDeleteProfilePhoto')" :body="`${t('settingsUserProfileZone.modalDeleteProfilePhotoBody')}`" actionButtonType="danger" :actionButtonText="t('settingsUserProfileZone.buttonDeleteProfilePhoto')" @submitAction="submitDeleteUserPhoto"/>

                <!-- Edit profile section -->
                <a class="mt-2 w-100 btn btn-primary" href="#" role="button" data-bs-toggle="modal" data-bs-target="#editProfileModal">{{ $t("settingsUserProfileZone.buttonEditProfile") }}</a>

                <!-- Modal edit user -->
                <UsersAddEditUserModalComponent :action="'profile'" :user="authStore.user"/>
            </div>
            <div class="col">
                <!-- user name -->
                <h2>{{ authStore.user.name }}</h2>
                <!-- user username -->
                <p><b>{{ $t("settingsUserProfileZone.usernameLabel") }}: </b>{{ authStore.user.username }}</p>
                <!-- user email -->
                <p><b>{{ $t("settingsUserProfileZone.emailLabel") }}: </b>{{ authStore.user.email }}</p>
                <!-- user city -->
                <p>
                    <b>{{ $t("settingsUserProfileZone.cityLabel") }}: </b>
                    <span v-if="authStore.user.city">{{ authStore.user.city }}</span>
                    <span v-else>{{ $t("generalItems.labelNotApplicable") }}</span>
                </p>
                <!-- user birthdate -->
                <p>
                    <b>{{ $t("settingsUserProfileZone.birthdayLabel") }}: </b>
                    <span v-if="authStore.user.birthdate">{{ authStore.user.birthdate }}</span>
                    <span v-else>{{ $t("generalItems.labelNotApplicable") }}</span>
                </p>
                <!-- user gender -->
                <p>
                    <b>{{ $t("settingsUserProfileZone.genderLabel") }}: </b>
                    <span v-if="authStore.user.gender == 1">{{ $t("settingsUserProfileZone.genderOption1") }}</span>
                    <span v-else>{{ $t("settingsUserProfileZone.genderOption2") }}</span>
                </p>
                <!-- user units -->
                <p>
                    <b>{{ $t("settingsUserProfileZone.unitsLabel") }}: </b>
                    <span v-if="Number(authStore?.user?.units) === 1">{{ $t("settingsUserProfileZone.unitsOption1") }}</span>
                    <span v-else>{{ $t("settingsUserProfileZone.unitsOption2") }}</span>
                </p>
                <!-- user height -->
                <p>
                    <b>{{ $t("settingsUserProfileZone.heightLabel") }} 
                        <span v-if="Number(authStore?.user?.units) === 1">({{ $t("generalItems.unitsCm") }}): </span>
                        <span v-else>({{ $t("generalItems.unitsFeetInches") }}): </span>
                    </b>
                    <span v-if="authStore.user.height">
                        <span v-if="Number(authStore?.user?.units) === 1">{{ authStore.user.height }}{{ $t("generalItems.unitsCm") }}</span>
                        <span v-else>{{ feet }}’{{ inches }}’’</span>
                    </span>
                    <span v-else>{{ $t("generalItems.labelNotApplicable") }}</span>
                </p>
                <!-- user preferred language -->
                <p>
                    <b>{{ $t("settingsUserProfileZone.preferredLanguageLabel") }}: </b>
                    <span v-if="authStore.user.preferred_language == 'us'">{{ $t("settingsUserProfileZone.preferredLanguageOption1") }}</span>
                    <span v-if="authStore.user.preferred_language == 'ca'">{{ $t("settingsUserProfileZone.preferredLanguageOption2") }}</span>
                    <span v-if="authStore.user.preferred_language == 'pt'">{{ $t("settingsUserProfileZone.preferredLanguageOption3") }}</span>
                    <span v-if="authStore.user.preferred_language == 'de'">{{ $t("settingsUserProfileZone.preferredLanguageOption4") }}</span>
                    <span v-if="authStore.user.preferred_language == 'fr'">{{ $t("settingsUserProfileZone.preferredLanguageOption5") }}</span>
                </p>
                <!-- user type -->
                <p>
                    <b>{{ $t("settingsUserProfileZone.accessTypeLabel") }}: </b>
                    <span v-if="authStore.user.access_type == 1">{{ $t("settingsUserProfileZone.accessTypeOption1") }}</span>
                    <span v-else>{{ $t("settingsUserProfileZone.accessTypeOption2") }}</span>
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
import ModalComponent from "@/components/Modals/ModalComponent.vue";

export default {
	components: {
		UserAvatarComponent,
		UsersAddEditUserModalComponent,
        ModalComponent,
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
				push.success(t("settingsUserProfileZone.userPhotoDeleteSuccess"));
			} catch (error) {
				// Show the error message
				push.error(
					`${t("settingsUserProfileZone.userPhotoDeleteError")} - ${error}`,
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