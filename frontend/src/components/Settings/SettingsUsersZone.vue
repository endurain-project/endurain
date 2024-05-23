<template>
    <div class="col">
        <ErrorToastComponent v-if="errorMessage" />
        <SuccessToastComponent v-if="successMessage" />

        <div class="row row-gap-3">
            <div class="col-lg-4 col-md-12">
                <!-- add user button -->
                <a class="w-100 btn btn-primary" href="#" role="button" data-bs-toggle="modal" data-bs-target="#addUserModal">{{ $t("settingsUsersZone.buttonAddUser") }}</a>

                <!-- Modal add user -->
                <div class="modal fade" id="addUserModal" tabindex="-1" aria-labelledby="addUserModal" aria-hidden="true">
                    <div class="modal-dialog">
                        <div class="modal-content">
                            <div class="modal-header">
                                <h1 class="modal-title fs-5" id="addUserModal">{{ $t("settingsUsersZone.buttonAddUser") }}</h1>
                                <button type="button" class="btn-close" data-bs-dismiss="modal" aria-label="Close"></button>
                            </div>
                            <form  @submit.prevent="submitAddUserForm">
                                <div class="modal-body">
                                    <!-- img fields -->
                                    <label for="userImgAdd"><b>{{ $t("settingsUsersZone.addUserModalUserPhotoLabel") }}</b></label>
                                    <input class="form-control" type="file" accept="image/*" name="userImgAdd" id="userImgAdd" @change="handleFileChange">
                                    <!-- username fields -->
                                    <label for="userUsernameAdd"><b>* {{ $t("settingsUsersZone.addUserModalUsernameLabel") }}</b></label>
                                    <input class="form-control" type="text" name="userUsernameAdd" :placeholder='$t("settingsUsersZone.addUserModalUsernamePlaceholder")' maxlength="45" v-model="newUserUsername" required>
                                    <!-- name fields -->
                                    <label for="userNameAdd"><b>* {{ $t("settingsUsersZone.addUserModalNameLabel") }}</b></label>
                                    <input class="form-control" type="text" name="userNameAdd" :placeholder='$t("settingsUsersZone.addUserModalNamePlaceholder")' maxlength="45" v-model="newUserName" required>
                                    <!-- email fields -->
                                    <label for="userEmailAdd"><b>* {{ $t("settingsUsersZone.addUserModalEmailLabel") }}</b></label>
                                    <input class="form-control" type="text" name="userEmailAdd" :placeholder='$t("settingsUsersZone.addUserModalEmailPlaceholder")' maxlength="45" v-model="newUserEmail" required>
                                    <!-- password fields -->
                                    <label for="passUserAdd"><b>* {{ $t("settingsUsersZone.addUserModalPasswordLabel") }}</b></label>
                                    <input class="form-control" :class="{ 'is-invalid': !isPasswordValid }" type="password" id="validationPassword" aria-describedby="validationPasswordFeedback" name="passUserAdd" :placeholder='$t("settingsUsersZone.addUserModalPasswordPlaceholder")' v-model="newUserPassword" required>
                                    <div id="validationPasswordFeedback" class="invalid-feedback" v-if="!isPasswordValid">
                                        {{ $t("usersListComponent.modalChangeUserPasswordFeedbackLabel") }}
                                    </div>
                                    <!-- city fields -->
                                    <label for="userCityAdd"><b>{{ $t("settingsUsersZone.addUserModalTownLabel") }}</b></label>
                                    <input class="form-control" type="text" name="userCityAdd" :placeholder='$t("settingsUsersZone.addUserModalTownPlaceholder")' maxlength="45" v-model="newUserTown">
                                    <!-- birth date fields -->
                                    <label for="userBirthDateAdd"><b>{{ $t("settingsUsersZone.addUserModalBirthdayLabel") }}</b></label>
                                    <input class="form-control" type="date" name="userBirthDateAdd" v-model="newUserBirthDate">
                                    <!-- gender fields -->
                                    <label for="userGenderAdd"><b>* {{ $t("settingsUsersZone.addUserModalGenderLabel") }}</b></label>
                                    <select class="form-control" name="userGenderAdd" v-model="newUserGender" required>
                                        <option value="1">{{ $t("settingsUsersZone.addUserModalGenderOption1") }}</option>
                                        <option value="2">{{ $t("settingsUsersZone.addUserModalGenderOption2") }}</option>
                                    </select>
                                    <!-- preferred language fields -->
                                    <label for="userPreferredLanguageAdd"><b>* {{ $t("settingsUsersZone.addUserModalUserPreferedLanguageLabel") }}</b></label>
                                    <select class="form-control" name="userPreferredLanguageAdd" v-model="newUserPreferredLanguage" required>
                                        <option value="en">{{ $t("settingsUsersZone.addUserModalPreferredLanguageOption1") }}</option>
                                    </select>
                                    <!-- access type fields -->
                                    <label for="userAccessTypeAdd"><b>* {{ $t("settingsUsersZone.addUserModalUserTypeLabel") }}</b></label>
                                    <select class="form-control" name="userAccessTypeAdd" v-model="newUserAccessType" required>
                                        <option value="1">{{ $t("settingsUsersZone.addUserModalUserTypeOption1") }}</option>
                                        <option value="2">{{ $t("settingsUsersZone.addUserModalUserTypeOption2") }}</option>
                                    </select>
                                    <p>* {{ $t("generalItens.requiredField") }}</p>
                                </div>
                                <div class="modal-footer">
                                    <button type="button" class="btn btn-secondary" data-bs-dismiss="modal">{{ $t("generalItens.buttonClose") }}</button>
                                    <button type="submit" class="btn btn-success" :disabled="!isPasswordValid" data-bs-dismiss="modal">{{ $t("settingsUsersZone.buttonAddUser") }}</button>
                                </div>
                            </form>
                        </div>
                    </div>
                </div>
            </div>
            <!-- form to search-->
            <div class="col">
                <form class="d-flex">
                    <input class="form-control me-2" type="text" name="userUsername" :placeholder='$t("settingsUsersZone.addUserModalUsernameLabel")' v-model="searchUsername" required>
                </form>
            </div>
        </div>
        <div>
            <LoadingComponent v-if="isLoading" />
            <div v-else>
                <!-- Checking if usersArray is loaded and has length -->
                <div v-if="usersArray && usersArray.length">
                    <!-- title zone -->
                    <br>
                    <p>{{ $t("settingsUsersZone.labelNumberOfUsers1") }}{{ usersNumber }}{{ $t("settingsUsersZone.labelNumberOfUsers2") }}{{ usersArray.length }}{{ $t("settingsUsersZone.labelNumberOfUsers3") }}</p>

                    <!-- list zone -->
                    <ul class="list-group list-group-flush"  v-for="user in usersArray" :key="user.id" :user="user">
                        <UsersListConponent :user="user" @userDeleted="updateUserList" />
                    </ul>
                </div>
                <!-- Displaying a message or component when there are no activities -->
                <div v-else>
                    <br>
                    <NoItemsFoundComponent />
                </div>
            </div>
        </div>
    </div>
</template>

<script>
import { ref, onMounted, onUnmounted, watch, computed } from 'vue';
import { useI18n } from 'vue-i18n';
// Importing the stores
import { useSuccessAlertStore } from '@/stores/Alerts/successAlert';
import { useErrorAlertStore } from '@/stores/Alerts/errorAlert';
// Importing the components
import ErrorToastComponent from '@/components/Toasts/ErrorToastComponent.vue';
import SuccessToastComponent from '@/components/Toasts/SuccessToastComponent.vue';
import LoadingComponent from '@/components/LoadingComponent.vue';
import NoItemsFoundComponent from '@/components/NoItemsFoundComponents.vue';
import UsersListConponent from '@/components/Settings/SettingsUsersZone/UsersListComponent.vue';
// Importing the services
import { users } from '@/services/user';
// Importing the crypto-js
import CryptoJS from 'crypto-js';

export default {
    components: {
        LoadingComponent,
        ErrorToastComponent,
        SuccessToastComponent,
        NoItemsFoundComponent,
        UsersListConponent
    },
    setup() {
        const { t } = useI18n();
        const errorAlertStore = useErrorAlertStore();
        const successAlertStore = useSuccessAlertStore();
        const isLoading = ref(true);
        const errorMessage = ref('');
        const successMessage = ref('');
        const newUserPhotoFile = ref(null);
        const newUserUsername = ref('');
        const newUserName = ref('');
        const newUserEmail = ref('');
        const newUserPassword = ref('');
        const isPasswordValid = computed(() => {
            const regex = /^(?=.*[A-Z])(?=.*\d)(?=.*[!@#$%^&*()_+])[A-Za-z\d!@#$%^&*()_+]{8,}$/;
            return regex.test(newUserPassword.value);
        });
        const newUserTown = ref(null);
        const newUserBirthDate = ref(null);
        const newUserGender = ref(1);
        const newUserPreferredLanguage = ref('en');
        const newUserAccessType = ref(1);
        const usersArray = ref([]);
        const usersNumber = ref(0);
        const hasMoreUsers = ref(true);
        const pageNumber = ref(1);
        const numRecords = 5;
        const searchUsername = ref('');

        async function handleFileChange(event) {
            if (event.target.files && event.target.files[0]) {
                newUserPhotoFile.value = event.target.files[0];
            } else {
                newUserPhotoFile.value = null;
            }
        }

        async function fetchMoreUsers() {
            // If the component is already loading or there are no more gears to fetch, return.
            if (isLoading.value || !hasMoreUsers.value) return;

            // Add 1 to the page number.
            pageNumber.value++;
            try {
                // Fetch the users with pagination.
                const newUsers = await users.getUsersWithPagination(pageNumber.value, numRecords);
                // Add the new users to the users array.
                Array.prototype.push.apply(usersArray.value, newUsers);

                // If there are no more gears to fetch, set userHasMoreGears to false.
                if ((pageNumber.value * numRecords) >= usersNumber.value) {
                    hasMoreUsers.value = false;
                }
            } catch (error) {
                // If there is an error, set the error message and show the error alert.
                errorMessage.value = t('generalItens.errorFetchingInfo') + " - " + error.toString();
                errorAlertStore.setAlertMessage(errorMessage.value);
            }
        }

        async function performSearch() {
            // If the search nickname is empty, reset the list to initial state.
            if (!searchUsername.value) {
                // Reset the list to the initial state when search text is cleared
                pageNumber.value = 1;
                hasMoreUsers.value = true;

                await fetchInitialUsers();

                return;
            }
            try {
                // Fetch the users based on the search username.
                usersArray.value = await users.getUserByUsername(searchUsername.value);
            } catch (error) {
                // If there is an error, set the error message and show the error alert.
                errorMessage.value = t('generalItens.errorFetchingInfo') + " - " + error.toString();
                errorAlertStore.setAlertMessage(errorMessage.value);
            }
        }

        function handleScroll() {
            // If the user has reached the bottom of the window, fetch more gears.
            const bottomOfWindow = document.documentElement.scrollTop + window.innerHeight === document.documentElement.offsetHeight;

            if (bottomOfWindow) {
                fetchMoreUsers();
            }
        }

        async function submitAddUserForm() {
            try {
                if (isPasswordValid.value) {

                    // Create the gear data object.
                    const data = {
                        name: newUserName.value,
                        username: newUserUsername.value,
                        email: newUserEmail.value,
                        city: newUserTown.value,
                        birthdate: newUserBirthDate.value,
                        preferred_language: newUserPreferredLanguage.value,
                        gender: newUserGender.value,
                        access_type: newUserAccessType.value,
                        photo_path: null,
                        photo_path_aux: null,
                        is_active: 1,
                        password: CryptoJS.SHA256(newUserPassword.value).toString(CryptoJS.enc.Hex),
                    };

                    // Create the gear and get the created gear id.
                    const createdUserId = await users.createUser(data);

                    // If there is a photo, upload it and get the photo url.
                    if (newUserPhotoFile.value) {
                        try {
                            await users.uploadImage(newUserPhotoFile.value, createdUserId);
                        } catch (error) {
                            // Set the error message
                            errorMessage.value = t('generalItens.errorFetchingInfo') + " - " + error.toString();
                            errorAlertStore.setAlertMessage(errorMessage.value);
                        }
                    }

                    // Get the created gear and add it to the userGears array.
                    const newUser = await users.getUserById(createdUserId);
                    usersArray.value.unshift(newUser);

                    // Increment the number of users.
                    usersNumber.value++;

                    // Set the success message and show the success alert.
                    successMessage.value = t('settingsUsersZone.successUserAdded');
                    successAlertStore.setAlertMessage(successMessage.value);
                    successAlertStore.setClosableState(true);
                }
            } catch(error) {
                // If there is an error, set the error message and show the error alert.
                errorMessage.value = t('generalItens.errorFetchingInfo') + " - " + error.toString();
                errorAlertStore.setAlertMessage(errorMessage.value);
            }
        }

        async function fetchInitialUsers() {
            try {
                // Fetch the users with pagination.
                usersArray.value = await users.getUsersWithPagination(pageNumber.value, numRecords);
                // Get the total number of user gears.
                usersNumber.value = await users.getUsersNumber();

                // If there are no more users to fetch, set hasMoreUsers to false.
                if ((pageNumber.value * numRecords) >= usersNumber.value) {
                    hasMoreUsers.value = false;
                }
            } catch (error) {
                // If there is an error, set the error message and show the error alert.
                errorMessage.value = t('generalItens.errorFetchingInfo') + " - " + error.toString();
                errorAlertStore.setAlertMessage(errorMessage.value);
            }
        }

        function updateUserList(userDeletedId) {
            usersArray.value = usersArray.value.filter(user => user.id !== userDeletedId);
            usersNumber.value--;

            successMessage.value = t('usersListComponent.userDeleteSuccessMessage');
            successAlertStore.setAlertMessage(successMessage.value);
            successAlertStore.setClosableState(true);
        }

        onMounted(async () => {
            // Add the event listener for scroll event.
            window.addEventListener('scroll', handleScroll);

            // Fetch the initial users.
            await fetchInitialUsers();

            // Set the isLoading to false.
            isLoading.value = false;
        });

        onUnmounted(() => {
            // Remove the event listener for scroll event.
            window.removeEventListener('scroll', handleScroll);
        });

        watch(searchUsername, performSearch, { immediate: false });

        return {
            t,
            isLoading,
            errorMessage,
            successMessage,
            newUserPhotoFile,
            newUserUsername,
            newUserName,
            newUserEmail,
            newUserPassword,
            isPasswordValid,
            newUserTown,
            newUserBirthDate,
            newUserGender,
            newUserPreferredLanguage,
            newUserAccessType,
            submitAddUserForm,
            handleFileChange,
            usersNumber,
            usersArray,
            searchUsername,
            updateUserList,
        };
    },
};
</script>