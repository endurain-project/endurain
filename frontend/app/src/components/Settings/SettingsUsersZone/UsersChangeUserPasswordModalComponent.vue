<template>
    <!-- change user password Modal -->
    <div class="modal fade" :id="`editUserPasswordModal${user.id}`"  tabindex="-1" :aria-labelledby="`editUserPasswordModal${user.id}`" aria-hidden="true">
        <div class="modal-dialog">
            <div class="modal-content">
                <div class="modal-header">
                    <h1 class="modal-title fs-5" :id="`editUserPasswordModal${user.id}`">{{ $t("usersChangeUserPasswordModalComponent.modalChangeUserPasswordTitle") }}</h1>
                    <button type="button" class="btn-close" data-bs-dismiss="modal" aria-label="Close"></button>
                </div>
                <form @submit.prevent="submitChangeUserPasswordForm">
                    <div class="modal-body">
                        <UsersPasswordRequirementsComponent />

                        <p>{{ $t("usersChangeUserPasswordModalComponent.modalChangeUserPasswordBodyLabel") }}<b>{{ user.username }}</b></p>

                        <!-- password fields -->
                        <label for="validationNewPassword"><b>* {{ $t("usersChangeUserPasswordModalComponent.modalChangeUserPasswordPasswordLabel") }}</b></label>
                        <input class="form-control" :class="{ 'is-invalid': !isNewPasswordValid || !isPasswordMatch }" type="password" id="validationNewPassword" aria-describedby="validationNewPasswordFeedback" :placeholder='$t("usersChangeUserPasswordModalComponent.modalChangeUserPasswordPasswordLabel")' v-model="newPassword" required>
                        <div id="validationNewPasswordFeedback" class="invalid-feedback" v-if="!isNewPasswordValid">
                            {{ $t("usersChangeUserPasswordModalComponent.modalChangeUserPasswordFeedbackLabel") }}
                        </div>
                        <div id="validationNewPasswordFeedback" class="invalid-feedback" v-if="!isPasswordMatch">
                            {{ $t("usersChangeUserPasswordModalComponent.modalChangeUserPasswordPasswordsDoNotMatchFeedbackLabel") }}
                        </div>
                        <!-- repeat password fields -->

                        <label class="mt-1" for="validationNewPasswordRepeat"><b>* {{ $t("usersChangeUserPasswordModalComponent.modalChangeUserPasswordPasswordConfirmationLabel") }}</b></label>
                        <input class="form-control" :class="{ 'is-invalid': !isNewPasswordRepeatValid || !isPasswordMatch }" type="password" id="validationNewPasswordRepeat" aria-describedby="validationNewPasswordRepeatFeedback" :placeholder='$t("usersChangeUserPasswordModalComponent.modalChangeUserPasswordPasswordConfirmationLabel")' v-model="newPasswordRepeat" required>
                        <div id="validationNewPasswordRepeatFeedback" class="invalid-feedback" v-if="!isNewPasswordRepeatValid">
                            {{ $t("usersChangeUserPasswordModalComponent.modalChangeUserPasswordFeedbackLabel") }}
                        </div>
                        <div id="validationNewPasswordRepeatFeedback" class="invalid-feedback" v-if="!isPasswordMatch">
                            {{ $t("usersChangeUserPasswordModalComponent.modalChangeUserPasswordPasswordsDoNotMatchFeedbackLabel") }}
                        </div>

                        <p>* {{ $t("generalItems.requiredField") }}</p>
                    </div>
                    <div class="modal-footer">
                        <button type="button" class="btn btn-secondary" data-bs-dismiss="modal">{{ $t("generalItems.buttonClose") }}</button>
                        <button type="submit" class="btn btn-success" :disabled="!isNewPasswordValid || !isNewPasswordRepeatValid || !isPasswordMatch" name="editUserPasswordAdmin" data-bs-dismiss="modal">{{ $t("usersChangeUserPasswordModalComponent.modalChangeUserPasswordTitle") }}</button>
                    </div>
                </form>
            </div>
        </div>
    </div>
</template>

<script>
import { ref, computed } from "vue";
import { useI18n } from "vue-i18n";
// Import Notivue push
import { push } from "notivue";
// Importing the services
import { users } from "@/services/usersService";
// Importing the components
import UsersPasswordRequirementsComponent from "@/components/Settings/SettingsUsersZone/UsersPasswordRequirementsComponent.vue";

export default {
	components: {
		UsersPasswordRequirementsComponent,
	},
    props: {
		user: {
			type: Object,
			required: true,
		},
	},
    setup(props) {
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
					await users.editUserPassword(props.user.id, data);
					// Set the success message and show the success alert.
					push.success(
						t("usersChangeUserPasswordModalComponent.userChangePasswordSuccessMessage"),
					);
				}
			} catch (error) {
				// If there is an error, set the error message and show the error alert.
				push.error(
					`${t("usersChangeUserPasswordModalComponent.userChangePasswordErrorMessage")} - ${error}`,
				);
			}
		}

        return {
			newPassword,
			newPasswordRepeat,
			isNewPasswordValid,
			isNewPasswordRepeatValid,
			isPasswordMatch,
			submitChangeUserPasswordForm,
		};
    },
};
</script>