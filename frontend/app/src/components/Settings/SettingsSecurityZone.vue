<template>
	<div class="col">
		<div class="bg-body-tertiary rounded p-3 shadow-sm">
			<h4>{{ $t("settingsSecurityZone.subtitleChangePassword") }}</h4>
			<UsersPasswordRequirementsComponent />

			<form @submit.prevent="submitChangeUserPasswordForm">
				<!-- password fields -->
				<label for="validationNewPassword"><b>* {{ $t("settingsSecurityZone.changeUserPasswordPasswordLabel") }}</b></label>
				<input class="form-control" :class="{ 'is-invalid': !isNewPasswordValid || !isPasswordMatch }" type="password" id="validationNewPassword" aria-describedby="validationNewPasswordFeedback" :placeholder='$t("settingsSecurityZone.changeUserPasswordPasswordLabel")' v-model="newPassword" required>
				<div id="validationNewPasswordFeedback" class="invalid-feedback" v-if="!isNewPasswordValid">
					{{ $t("settingsSecurityZone.changeUserPasswordFeedbackLabel") }}
				</div>
				<div id="validationNewPasswordFeedback" class="invalid-feedback" v-if="!isPasswordMatch">
					{{ $t("settingsSecurityZone.changeUserPasswordPasswordsDoNotMatchFeedbackLabel") }}
				</div>

				<!-- repeat password fields -->
				<label class="mt-1" for="validationNewPasswordRepeat"><b>* {{ $t("settingsSecurityZone.changeUserPasswordPasswordConfirmationLabel") }}</b></label>
				<input class="form-control" :class="{ 'is-invalid': !isNewPasswordRepeatValid || !isPasswordMatch }" type="password" id="validationNewPasswordRepeat" aria-describedby="validationNewPasswordRepeatFeedback" :placeholder='$t("settingsSecurityZone.changeUserPasswordPasswordConfirmationLabel")' v-model="newPasswordRepeat" required>
				<div id="validationNewPasswordRepeatFeedback" class="invalid-feedback" v-if="!isNewPasswordRepeatValid">
					{{ $t("settingsSecurityZone.changeUserPasswordFeedbackLabel") }}
				</div>
				<div id="validationNewPasswordRepeatFeedback" class="invalid-feedback" v-if="!isPasswordMatch">
					{{ $t("settingsSecurityZone.changeUserPasswordPasswordsDoNotMatchFeedbackLabel") }}
				</div>

				<p>* {{ $t("generalItems.requiredField") }}</p>

				<button type="submit" class="btn btn-success" :disabled="!isNewPasswordValid || !isNewPasswordRepeatValid || !isPasswordMatch" name="editUserPassword">{{ $t("settingsSecurityZone.subtitleChangePassword") }}</button>
			</form>

			<hr>
			<!-- user sessions list -->
			<h4>{{ $t("settingsSecurityZone.subtitleMySessions") }}</h4>
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
	</div>
</template>

<script>
import { ref, computed, onMounted } from "vue";
import { useI18n } from "vue-i18n";
// Importing the services
import { profile } from "@/services/profileService";
// Import Notivue push
import { push } from "notivue";
// Importing the components
import UsersPasswordRequirementsComponent from "@/components/Settings/SettingsUsersZone/UsersPasswordRequirementsComponent.vue";
import LoadingComponent from "@/components/GeneralComponents/LoadingComponent.vue";
import NoItemsFoundComponents from "@/components/GeneralComponents/NoItemsFoundComponents.vue";
import UserSessionsListComponent from "@/components/Settings/SettingsUserSessionsZone/UserSessionsListComponent.vue";

export default {
	components: {
		UsersPasswordRequirementsComponent,
		LoadingComponent,
		NoItemsFoundComponents,
		UserSessionsListComponent,
	},
	setup() {
		const { t } = useI18n();
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
		const userSessions = ref([]);
		const isLoading = ref(true);

		async function submitChangeUserPasswordForm() {
			try {
				if (
					isNewPasswordValid.value &&
					isNewPasswordRepeatValid.value &&
					isPasswordMatch.value
				) {
					// Create the data object to send to the service.
					const data = {
						password: newPassword.value,
					};

					// Call the service to edit the user password.
					await profile.editProfilePassword(data);

					// Show the success alert.
					push.success(
						t("settingsSecurityZone.userChangePasswordSuccessMessage"),
					);
				}
			} catch (error) {
				// If there is an error, show the error alert.
				push.error(
					`${t("settingsSecurityZone.userChangePasswordErrorMessage")} - ${error}`,
				);
			}
		}

		async function updateSessionListDeleted(sessionDeletedId) {
			try {
				// Delete session in the DB
				await profile.deleteProfileSession(sessionDeletedId);

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
			userSessions.value = await profile.getProfileSessions();

			// Set the isLoading to false
			isLoading.value = false;
		});

		return {
			t,
			newPassword,
			newPasswordRepeat,
			isNewPasswordValid,
			isNewPasswordRepeatValid,
			isPasswordMatch,
			submitChangeUserPasswordForm,
			userSessions,
			isLoading,
			updateSessionListDeleted,
		};
	},
};
</script>