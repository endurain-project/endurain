<template>
    <div class="col">
        <ErrorToastComponent v-if="errorMessage" />
        <SuccessToastComponent v-if="successMessage" />
        
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
import { users } from '@/services/user';
// Importing the stores
import { useSuccessAlertStore } from '@/stores/Alerts/successAlert';
import { useErrorAlertStore } from '@/stores/Alerts/errorAlert';
// Importing the components
import ErrorToastComponent from '@/components/Toasts/ErrorToastComponent.vue';
import SuccessToastComponent from '@/components/Toasts/SuccessToastComponent.vue';
import SettingsPasswordRequirementsComponent from '@/components/Settings/SettingsPasswordRequirementsComponent.vue';
// Importing the crypto-js
import CryptoJS from 'crypto-js';

export default {
    components: {
        ErrorToastComponent,
        SuccessToastComponent,
        SettingsPasswordRequirementsComponent,
    },
    setup() {
        const userMe = JSON.parse(localStorage.getItem('userMe'));
        const { t } = useI18n();
        const errorAlertStore = useErrorAlertStore();
        const successAlertStore = useSuccessAlertStore();
        const errorMessage = ref('');
        const successMessage = ref('');
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

        function resetMessageValues() {
            successMessage.value = '';
            successAlertStore.setAlertMessage(successMessage.value);
            errorMessage.value = '';
            errorAlertStore.setAlertMessage(errorMessage.value);
        }

        async function submitChangeUserPasswordForm() {
            resetMessageValues();

            try{
                if (isNewPasswordValid.value && isNewPasswordRepeatValid.value && isPasswordMatch.value) {
                    const data = {
                        id: userMe.id,
                        password: CryptoJS.SHA256(newPassword.value).toString(CryptoJS.enc.Hex),
                    };
                    await users.editUserPassword(data);
                    // Set the success message and show the success alert.
                    successMessage.value = t('usersListComponent.userChangePasswordSuccessMessage');
                    successAlertStore.setAlertMessage(successMessage.value);
                    successAlertStore.setClosableState(true);
                }
            } catch (error) {
                // If there is an error, set the error message and show the error alert.
                errorMessage.value = t('usersListComponent.userChangePasswordErrorMessage') + " - " + error.toString();
                errorAlertStore.setAlertMessage(errorMessage.value);
            }
        }

        return {
            t,
            errorMessage,
            successMessage,
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