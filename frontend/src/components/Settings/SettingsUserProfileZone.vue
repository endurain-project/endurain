<template>
    <div class="col">
        <ErrorToastComponent v-if="errorMessage" />
        <SuccessToastComponent v-if="successMessage" />

        <div class="row row-gap-3">
            <div class="col-lg-4 col-md-12">
                <div class="justify-content-center align-items-center d-flex">
                    <UserAvatarComponent :userProp="userMe" :width=180 :height=180 />
                </div>

                <!-- Delete profile photo section -->
                <a class="mt-4 w-100 btn btn-danger" href="#" role="button" data-bs-toggle="modal" data-bs-target="#deleteProfilePhotoModal" v-if="userMe.photo_path">{{ $t("settingsUserProfileZone.buttonDeleteProfilePhoto") }}</a>

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
                                <button type="button" class="btn btn-secondary" data-bs-dismiss="modal">{{ $t("generalItens.buttonClose") }}</button>
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
                                            <div class="col" v-if="userMe.photo_path">
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
                                    <!-- preferred language fields -->
                                    <label for="userPreferredLanguageEdit"><b>* {{ $t("settingsUsersZone.addUserModalUserPreferedLanguageLabel") }}</b></label>
                                    <select class="form-control" name="userPreferredLanguageEdit" v-model="editUserPreferredLanguage" required>
                                        <option value="en">{{ $t("settingsUsersZone.addUserModalPreferredLanguageOption1") }}</option>
                                    </select>
                                    <p>* {{ $t("generalItens.requiredField") }}</p>
                                </div>
                                <div class="modal-footer">
                                    <button type="button" class="btn btn-secondary" data-bs-dismiss="modal">{{ $t("generalItens.buttonClose") }}</button>
                                    <button type="submit" class="btn btn-success" name="userEdit" data-bs-dismiss="modal">{{ $t("usersListComponent.modalEditUserTitle") }}</button>
                                </div>
                            </form>
                        </div>
                    </div>
                </div>
            </div>
            <div class="col">
                <h2>{{ userMe.name }}</h2>
                <p><b>{{ $t("settingsUsersZone.addUserModalUsernameLabel") }}: </b>{{ userMe.username }}</p>
                <p><b>{{ $t("settingsUsersZone.addUserModalEmailLabel") }}: </b>{{ userMe.email }}</p>
                <p>
                    <b>{{ $t("settingsUsersZone.addUserModalTownLabel") }}: </b>
                    <span v-if="userMe.birthdate">{{ userMe.birthdate }}</span>
                    <span v-else>N/A</span>
                </p>
                <p>
                    <b>{{ $t("settingsUsersZone.addUserModalBirthdayLabel") }}: </b>
                    <span v-if="userMe.city">{{ userMe.city }}</span>
                    <span v-else>N/A</span>
                </p>
                <p>
                    <b>{{ $t("settingsUsersZone.addUserModalGenderLabel") }}: </b>
                    <span v-if="userMe.gender == 1">{{ $t("settingsUsersZone.addUserModalGenderOption1") }}</span>
                    <span v-else>{{ $t("settingsUsersZone.addUserModalGenderOption2") }}</span>
                </p>
                <p>
                    <b>{{ $t("settingsUsersZone.addUserModalUserPreferedLanguageLabel") }}: </b>
                    <span v-if="userMe.preferred_language == 'en'">{{ $t("settingsUsersZone.addUserModalPreferredLanguageOption1") }}</span>
                </p>
                <p>
                    <b>{{ $t("settingsUsersZone.addUserModalUserTypeLabel") }}: </b>
                    <span v-if="userMe.access_type == 1">{{ $t("settingsUsersZone.addUserModalUserTypeOption1") }}</span>
                    <span v-else>{{ $t("settingsUsersZone.addUserModalUserTypeOption2") }}</span>
                </p>
            </div>
        </div>
    </div>
</template>

<script>
import { ref } from 'vue';
import { useI18n } from 'vue-i18n';
// Importing the services
import { users } from '@/services/user';
// Importing the stores
import { useSuccessAlertStore } from '@/stores/Alerts/successAlert';
import { useErrorAlertStore } from '@/stores/Alerts/errorAlert';
// Importing the components
import ErrorToastComponent from '@/components/Toasts/ErrorToastComponent.vue';
import SuccessToastComponent from '@/components/Toasts/SuccessToastComponent.vue';
import UserAvatarComponent from '../Users/UserAvatarComponent.vue';

export default {
    components: {
        ErrorToastComponent,
        SuccessToastComponent,
        UserAvatarComponent,
    },
    setup() {
        const userMe = ref(JSON.parse(localStorage.getItem('userMe')));
        const { t } = useI18n();
        const errorAlertStore = useErrorAlertStore();
        const successAlertStore = useSuccessAlertStore();
        const errorMessage = ref('');
        const successMessage = ref('');
        const editUserPhotoFile = ref(null);
        const editUserUsername = ref(userMe.value.username);
        const editUserName = ref(userMe.value.name);
        const editUserEmail = ref(userMe.value.email);
        const editUserTown = ref(userMe.value.city);
        const editUserBirthdate = ref(userMe.value.birthdate);
        const editUserGender = ref(userMe.value.gender);
        const editUserPreferredLanguage = ref(userMe.value.preferred_language);
        const editUserAccessType = ref(userMe.value.access_type);

        function resetMessageValues() {
            successMessage.value = '';
            successAlertStore.setAlertMessage(successMessage.value);
            errorMessage.value = '';
            errorAlertStore.setAlertMessage(errorMessage.value);
        }

        async function handleFileChange(event) {
            if (event.target.files && event.target.files[0]) {
                editUserPhotoFile.value = event.target.files[0];
            } else {
                editUserPhotoFile.value = null;
            }
        }

        async function submitEditUserForm() {
            resetMessageValues();

            try {
                const data = {
                    id: userMe.value.id,
                    username: editUserUsername.value,
                    name: editUserName.value,
                    email: editUserEmail.value,
                    city: editUserTown.value,
                    birthdate: editUserBirthdate.value,
                    gender: editUserGender.value,
                    preferred_language: editUserPreferredLanguage.value,
                    access_type: editUserAccessType.value,
                    photo_path: null,
                    photo_path_aux: null,
                    is_active: 1,
                };

                await users.editUser(data);

                // If there is a photo, upload it and get the photo url.
                if (editUserPhotoFile.value) {
                    try {
                        userMe.value.photo_path = await users.uploadImage(editUserPhotoFile.value, userMe.value.id);
                    } catch (error) {
                        // Set the error message
                        errorMessage.value = t('generalItens.errorFetchingInfo') + " - " + error.toString();
                        errorAlertStore.setAlertMessage(errorMessage.value);
                    }
                }

                userMe.value.username = editUserUsername.value;
                userMe.value.name = editUserName.value;
                userMe.value.email = editUserEmail.value;
                userMe.value.city = editUserTown.value;
                userMe.value.birthdate = editUserBirthdate.value;
                userMe.value.city = editUserTown.value;
                userMe.value.birthdate = editUserBirthdate.value;
                userMe.value.gender = editUserGender.value;
                userMe.value.preferred_language = editUserPreferredLanguage.value;

                localStorage.setItem('userMe', JSON.stringify(userMe.value));

                // Set the success message and show the success alert.
                successMessage.value = t('usersListComponent.userEditSuccessMessage');
                successAlertStore.setAlertMessage(successMessage.value);
                successAlertStore.setClosableState(true);
            } catch (error) {
                // If there is an error, set the error message and show the error alert.
                errorMessage.value = t('usersListComponent.userEditErrorMessage') + " - " + error.toString();
                errorAlertStore.setAlertMessage(errorMessage.value);
            }
        }

        async function submitDeleteUserPhoto() {
            resetMessageValues();

            try {
                await users.deleteUserPhoto(userMe.value.id);
                userMe.value.photo_path = null;

                localStorage.setItem('userMe', JSON.stringify(userMe.value));

                // Set the success message and show the success alert.
                successMessage.value = t('usersListComponent.userPhotoDeleteSuccessMessage');
                successAlertStore.setAlertMessage(successMessage.value);
                successAlertStore.setClosableState(true);
            } catch (error) {
                // Set the error message
                errorMessage.value = t('usersListComponent.userPhotoDeleteErrorMessage') + " - " + error.toString();
                errorAlertStore.setAlertMessage(errorMessage.value);
            }
        }

        return {
            userMe,
            t,
            errorMessage,
            successMessage,
            editUserUsername,
            editUserName,
            editUserEmail,
            editUserTown,
            editUserBirthdate,
            editUserGender,
            editUserPreferredLanguage,
            editUserAccessType,
            submitEditUserForm,
            submitDeleteUserPhoto,
            handleFileChange,
        };
    },
};
</script>