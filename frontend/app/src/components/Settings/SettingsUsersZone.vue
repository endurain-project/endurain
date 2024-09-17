<template>
    <div class="col">
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

                    <!-- Displaying loading new gear if applicable -->
                    <ul class="list-group list-group-flush" v-if="isLoadingNewUser">
                        <li class="list-group-item rounded">
                            <LoadingComponent />
                        </li>
                    </ul>

                    <!-- Displaying loading if gears are updating -->
                    <LoadingComponent v-if="isUsersUpdatingLoading"/>

                    <!-- list zone -->
                    <ul class="list-group list-group-flush"  v-for="user in usersArray" :key="user.id" :user="user" v-else>
                        <UsersListComponent :user="user" @userDeleted="updateUserList" />
                    </ul>

                    <!-- pagination area -->
                    <PaginationComponent :totalPages="totalPages" :pageNumber="pageNumber" @pageNumberChanged="setPageNumber" v-if="!searchUsername"/>
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
import { ref, onMounted, watch, computed } from "vue";
import { useI18n } from "vue-i18n";
// Import Notivue push
import { push } from "notivue";
// import lodash
import { debounce } from "lodash";
// Importing the components
import LoadingComponent from "@/components/GeneralComponents/LoadingComponent.vue";
import NoItemsFoundComponent from "@/components/GeneralComponents/NoItemsFoundComponents.vue";
import UsersListComponent from "@/components/Settings/SettingsUsersZone/UsersListComponent.vue";
import PaginationComponent from "@/components/GeneralComponents/PaginationComponent.vue";
// Importing the services
import { users } from "@/services/usersService";

export default {
	components: {
		LoadingComponent,
		NoItemsFoundComponent,
		PaginationComponent,
		UsersListComponent,
	},
	setup() {
		const { t } = useI18n();
		const isLoading = ref(true);
		const isUsersUpdatingLoading = ref(false);
		const isLoadingNewUser = ref(false);
		const newUserPhotoFile = ref(null);
		const newUserUsername = ref("");
		const newUserName = ref("");
		const newUserEmail = ref("");
		const newUserPassword = ref("");
		const isPasswordValid = computed(() => {
			const regex =
				/^(?=.*[A-Z])(?=.*\d)(?=.*[ !\"#$%&'()*+,\-./:;<=>?@[\\\]^_`{|}~])[A-Za-z\d !"#$%&'()*+,\-./:;<=>?@[\\\]^_`{|}~]{8,}$/;
			return regex.test(newUserPassword.value);
		});
		const newUserTown = ref(null);
		const newUserBirthDate = ref(null);
		const newUserGender = ref(1);
		const newUserPreferredLanguage = ref("en");
		const newUserAccessType = ref(1);
		const usersArray = ref([]);
		const usersNumber = ref(0);
		const pageNumber = ref(1);
		const numRecords = 5;
		const totalPages = ref(1);
		const searchUsername = ref("");

		async function handleFileChange(event) {
			newUserPhotoFile.value = event.target.files?.[0] ?? null;
		}

		const performSearch = debounce(async () => {
			// If the search nickname is empty, reset the list to initial state.
			if (!searchUsername.value) {
				// Reset the list to the initial state when search text is cleared
				pageNumber.value = 1;

				await fetchUsers();

				return;
			}
			try {
				// Fetch the users based on the search username.
				usersArray.value = await users.getUserByUsername(searchUsername.value);
			} catch (error) {
				// If there is an error, set the error message and show the error alert.
				push.error(`${t("generalItens.errorFetchingInfo")} - ${error}`);
			}
		}, 500);

		async function submitAddUserForm() {
			isLoadingNewUser.value = true;
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
						is_active: 1,
						password: newUserPassword.value,
					};

					// Create the gear and get the created gear id.
					const createdUserId = await users.createUser(data);

					// If there is a photo, upload it and get the photo url.
					if (newUserPhotoFile.value) {
						try {
							await users.uploadImage(newUserPhotoFile.value, createdUserId);
						} catch (error) {
							// Set the error message
							push.error(`${t("generalItens.errorFetchingInfo")} - ${error}`);
						}
					}

					// Get the created gear and add it to the userGears array.
					const newUser = await users.getUserById(createdUserId);
					usersArray.value.unshift(newUser);

					// Increment the number of users.
					usersNumber.value++;

					// Set the success message and show the success alert.
					push.success(t("settingsUsersZone.successUserAdded"));
				}
			} catch (error) {
				// If there is an error, set the error message and show the error alert.
				push.error(`${t("generalItens.errorFetchingInfo")} - ${error}`);
			} finally {
				// Set the loading variable to false.
				isLoadingNewUser.value = false;
			}
		}

		function setPageNumber(page) {
			// Set the page number.
			pageNumber.value = page;
		}

		async function updateUsers() {
			try {
				// Set the loading variable to true.
				isUsersUpdatingLoading.value = true;

				// Fetch the gears with pagination.
				usersArray.value = await users.getUsersWithPagination(
					pageNumber.value,
					numRecords,
				);

				// Set the loading variable to false.
				isUsersUpdatingLoading.value = false;
			} catch (error) {
				// If there is an error, set the error message and show the error alert.
				push.error(`${t("generalItens.errorFetchingInfo")} - ${error}`);
			}
		}

		async function fetchUsers() {
			try {
				// Fetch the users with pagination.
				updateUsers();

				// Get the total number of user gears.
				usersNumber.value = await users.getUsersNumber();

				// Update total pages
				totalPages.value = Math.ceil(usersNumber.value / numRecords);
			} catch (error) {
				// If there is an error, set the error message and show the error alert.
				push.error(`${t("generalItens.errorFetchingInfo")} - ${error}`);
			}
		}

		function updateUserList(userDeletedId) {
			usersArray.value = usersArray.value.filter(
				(user) => user.id !== userDeletedId,
			);
			usersNumber.value--;

			push.success(t("usersListComponent.userDeleteSuccessMessage"));
		}

		onMounted(async () => {
			// Fetch the users.
			await fetchUsers();

			// Set the isLoading to false.
			isLoading.value = false;
		});

		// Watch the search username variable.
		watch(searchUsername, performSearch, { immediate: false });

		// Watch the page number variable.
		watch(pageNumber, updateUsers, { immediate: false });

		return {
			t,
			isLoading,
			isUsersUpdatingLoading,
			isLoadingNewUser,
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
			pageNumber,
			totalPages,
			setPageNumber,
			handleFileChange,
			usersNumber,
			usersArray,
			searchUsername,
			updateUserList,
		};
	},
};
</script>