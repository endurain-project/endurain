<template>
    <div class="col">
        <h4>{{ $t("settingsSecurityZone.subtitleChangePassword") }}</h4>
        <SettingsPasswordRequirementsComponent />

        <form @submit.prevent="submitChangeUserPasswordForm">
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

            <p>* {{ $t("generalItens.requiredField") }}</p>

            <button type="submit" class="btn btn-success" name="editUserPassword">{{ $t("settingsSecurityZone.subtitleChangePassword") }}</button>
        </form>
    </div>
</template>

<script>
import { ref, computed } from 'vue';
import { useI18n } from 'vue-i18n';
// Importing the services
import { profile } from '@/services/profileService';
// Importing the utils
import { addToast } from '@/utils/toastUtils';
// Importing the components
import SettingsPasswordRequirementsComponent from '@/components/Settings/SettingsPasswordRequirementsComponent.vue';

export default {
    components: {
        SettingsPasswordRequirementsComponent,
    },
    setup() {
        const { t } = useI18n();
        const newPassword = ref('');
        const newPasswordRepeat = ref('');
        const isNewPasswordValid = computed(() => {
            const regex = /^(?=.*[A-Z])(?=.*\d)(?=.*[!@#$%^&*()_+])[A-Za-z\d!@#$%^&*()_+]{8,}$/;
            return regex.test(newPassword.value);
        });
        const isNewPasswordRepeatValid = computed(() => {
            const regex = /^(?=.*[A-Z])(?=.*\d)(?=.*[!@#$%^&*()_+])[A-Za-z\d!@#$%^&*()_+]{8,}$/;
            return regex.test(newPasswordRepeat.value);
        });
        const isPasswordMatch = computed(() => newPassword.value === newPasswordRepeat.value);

        async function submitChangeUserPasswordForm() {
            try{
                if (isNewPasswordValid.value && isNewPasswordRepeatValid.value && isPasswordMatch.value) {
                    // Create the data object to send to the service.
                    const data = {
                        password: newPassword.value,
                    };

                    // Call the service to edit the user password.
                    await profile.editProfilePassword(data);

                    // Set the success message and show the success alert.
                    addToast(t('usersListComponent.userChangePasswordSuccessMessage'), 'success', true);
                }
            } catch (error) {
                // If there is an error, set the error message and show the error alert.
                addToast(t('usersListComponent.userChangePasswordErrorMessage') + " - " + error, 'danger', true);
            }
        }

        return {
            t,
            newPassword,
            newPasswordRepeat,
            isNewPasswordValid,
            isNewPasswordRepeatValid,
            isPasswordMatch,
            submitChangeUserPasswordForm
        };
    },
};
</script>