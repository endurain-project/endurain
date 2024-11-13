<template>
    <!-- Modal Garmin Connect authentication -->
    <div class="modal fade" id="garminConnectAuthModal" tabindex="-1" aria-labelledby="garminConnectAuthModal" aria-hidden="true">
        <div class="modal-dialog">
            <div class="modal-content">
                <div class="modal-header">
                    <h1 class="modal-title fs-5" id="garminConnectAuthModal">{{ $t("garminConnectLoginModalComponent.garminConnectAuthModalTitle") }}</h1>
                    <button type="button" class="btn-close" data-bs-dismiss="modal" aria-label="Close"></button>
                </div>
                <form  @submit.prevent="submitConnectGarminConnect">
                    <div class="modal-body">
                        <label for="userUsernameAdd"><b>* {{ $t("garminConnectLoginModalComponent.garminConnectAuthModalUsernameLabel") }}</b></label>
                        <input class="form-control" type="text" name="userUsernameAdd" :placeholder='$t("garminConnectLoginModalComponent.garminConnectAuthModalUsernamePlaceholder")' v-model="garminConnectUsername" required>
                        <!-- password fields -->
                        <label for="passUserAdd"><b>* {{ $t("garminConnectLoginModalComponent.garminConnectAuthModalPasswordLabel") }}</b></label>
                        <input class="form-control" type="password" name="passUserAdd" :placeholder='$t("garminConnectLoginModalComponent.garminConnectAuthModalPasswordPlaceholder")' v-model="garminConnectPassword" required>
                        <p>* {{ $t("generalItems.requiredField") }}</p>
                    </div>
                    <div class="modal-footer">
                        <button type="button" class="btn btn-secondary" data-bs-dismiss="modal">{{ $t("generalItems.buttonClose") }}</button>
                        <button type="submit" class="btn btn-success" data-bs-dismiss="modal">{{ $t("garminConnectLoginModalComponent.garminConnectAuthModalLoginButton") }}</button>
                    </div>
                </form>
            </div>
        </div>
    </div>
</template>

<script>
import { ref } from "vue";
import { useI18n } from "vue-i18n";
// Importing the stores
import { useAuthStore } from "@/stores/authStore";
// Import Notivue push
import { push } from "notivue";
// Importing the services
import { garminConnect } from "@/services/garminConnectService";

//import Modal from 'bootstrap/js/dist/modal';

export default {
	components: {},
	setup() {
		const authStore = useAuthStore();
		const { locale, t } = useI18n();
		const garminConnectUsername = ref("");
		const garminConnectPassword = ref("");

		async function submitConnectGarminConnect() {
            // Set the loading message
            const notification = push.promise(t('garminConnectLoginModalComponent.processingMessageLinkGarminConnect'));
			try {
				const data = {
                    username: garminConnectUsername.value,
                    password: garminConnectPassword.value,
                }; 
				await garminConnect.linkGarminConnect(data);

                // Set the user object with the is_garminconnect_linked property set to 1.
                const user = authStore.user;
                user.is_garminconnect_linked = 1;
                authStore.setUser(user, locale);

				// Show success message
				notification.resolve(t("garminConnectLoginModalComponent.successMessageLinkGarminConnect"));
			} catch (error) {
				// If there is an error, show the error alert.
				notification.reject(
					`${t("garminConnectLoginModalComponent.errorMessageUnableToLinkGarminConnect")} - ${error}`,
				);
			}
		}

		return {
			t,
			garminConnectUsername,
			garminConnectPassword,
			submitConnectGarminConnect,
		};
	},
};
</script>