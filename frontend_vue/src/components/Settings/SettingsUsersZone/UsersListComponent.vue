<template>
    <ErrorToastComponent v-if="errorMessage" />
    <SuccessToastComponent v-if="successMessage" />
    <li class="list-group-item d-flex justify-content-between">
        <div class="d-flex align-items-center">
            <img :src="userProp.photo_path" alt="User Photo" width="55" height="55" class="rounded-circle" v-if="userProp.photo_path">
            <img src="/src/assets/avatar/male1.png" alt="Default Male Avatar" width="55" height="55" class="rounded-circle" v-else-if="!userProp.photo_path && userProp.gender == 1">
            <img src="/src/assets/avatar/female1.png" alt="Default Female Avatar" width="55" height="55" class="rounded-circle" v-else>
            <div class="ms-3">
                <div class="fw-bold">
                    {{ userProp.username }}
                </div>
                <b>{{ $t("usersListComponent.userListAccessTypeLabel") }}</b>
                <span v-if="userProp.access_type == 1">{{ $t("usersListComponent.userListAccessTypeOption1") }}</span>
                <span v-else>{{ $t("usersListComponent.userListAccessTypeOption2") }}</span>
            </div>
        </div>
        <div>
            <span class="badge bg-success-subtle border border-success-subtle text-success-emphasis rounded-pill align-middle" v-if="user.is_active == 1">{{ $t("usersListComponent.userListUserIsActiveBadge") }}</span>
            <span class="badge bg-danger-subtle border border-danger-subtle text-danger-emphasis rounded-pill align-middle" v-else>{{ $t("usersListComponent.userListUserIsInactiveBadge") }}</span>

            <!-- change user password button -->
            <a class="btn btn-link btn-lg link-body-emphasis" href="#" role="button" data-bs-toggle="modal" :data-bs-target="`#editUserPasswordModal${userProp.id}`"><font-awesome-icon :icon="['fas', 'fa-key']" /></a>

            <!-- change user password Modal -->
            <div class="modal fade" :id="`editUserPasswordModal${userProp.id}`" tabindex="-1" :aria-labelledby="`editUserPasswordModal${userProp.id}`" aria-hidden="true">
                <div class="modal-dialog">
                    <div class="modal-content">
                        <div class="modal-header">
                            <h1 class="modal-title fs-5" :id="`editUserPasswordModal${userProp.id}`">{{ $t("usersListComponent.modalChangeUserPasswordTitle") }}</h1>
                            <button type="button" class="btn-close" data-bs-dismiss="modal" aria-label="Close"></button>
                        </div>
                        <form @submit.prevent="submitChangeUserPasswordForm">
                            <div class="modal-body">
                                <!-- info banner to display password complexity requirements -->
                                <div class="alert alert-info alert-dismissible d-flex align-items-center" role="alert">
                                    <!--<i class="fa-solid fa-circle-info me-1 allign-top"></i>-->
                                    <div>
                                        {{ $t("usersListComponent.modalChangeUserPasswordPasswordRequirementsTitle") }}
                                        <br>
                                        {{ $t("usersListComponent.modalChangeUserPasswordCharacters") }}
                                        <br>
                                        {{ $t("usersListComponent.modalChangeUserPasswordCapitalLetters") }}
                                        <br>
                                        {{ $t("usersListComponent.modalChangeUserPasswordNumbers") }}
                                        <br>
                                        {{ $t("usersListComponent.modalChangeUserPasswordSpecialCharacters") }}
                                    </div>
                                </div>

                                <p>{{ $t("usersListComponent.modalChangeUserPasswordBodyLabel") }}<b>{{ userProp.username }}</b></p>

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
                            </div>
                            <div class="modal-footer">
                                <button type="button" class="btn btn-secondary" data-bs-dismiss="modal">{{ $t("generalItens.buttonClose") }}</button>

                                <button type="submit" class="btn btn-success" :disabled="!isNewPasswordValid || !isNewPasswordRepeatValid || !isPasswordMatch" name="editUserPasswordAdmin" data-bs-dismiss="modal">{{ $t("usersListComponent.modalChangeUserPasswordTitle") }}</button>
                            </div>
                        </form>
                    </div>
                </div>
            </div>
        </div>
    </li>
</template>

<script>
import { ref, onMounted, onUnmounted, computed } from 'vue';
import { useI18n } from 'vue-i18n';
// Importing the services
import { users } from '@/services/user';
// Importing the stores
import { useSuccessAlertStore } from '@/stores/Alerts/successAlert';
import { useErrorAlertStore } from '@/stores/Alerts/errorAlert';
// Importing the components
import ErrorToastComponent from '@/components/Toasts/ErrorToastComponent.vue';
import SuccessToastComponent from '@/components/Toasts/SuccessToastComponent.vue';
// Importing the crypto-js
import CryptoJS from 'crypto-js';

export default {
    components: {
        ErrorToastComponent,
        SuccessToastComponent,
    },
    props: {
        user: {
            type: Object,
            required: true,
        }
    },
    setup(props) {
        const { t } = useI18n();
        const errorAlertStore = useErrorAlertStore();
        const successAlertStore = useSuccessAlertStore();
        const errorMessage = ref('');
        const successMessage = ref('');
        const userProp = ref(props.user);
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
            successMessage.value = '';
            successAlertStore.setAlertMessage(successMessage.value);
            errorMessage.value = '';
            errorAlertStore.setAlertMessage(errorMessage.value);
            try{
                if (isNewPasswordValid.value && isNewPasswordRepeatValid.value && isPasswordMatch.value) {
                    const data = {
                        id: userProp.value.id,
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
            userProp,
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