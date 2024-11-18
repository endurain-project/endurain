<template>
    <div class="col">
        <!-- list zone -->
        <ul class="list-group list-group-flush">
            <!-- strava zone -->
            <li class="list-group-item d-flex justify-content-between">
                <div class="d-flex align-items-center">
                    <font-awesome-icon class="me-2" :icon="['fab', 'strava']" size="2x" />
                    <div class="ms-3">
                        <div class="fw-bold">
                            {{ $t("settingsIntegrationsZone.stravaIntegrationTitle") }}
                        </div>
                        {{ $t("settingsIntegrationsZone.stravaIntegrationBody") }}
                    </div>
                </div>
                <div class="d-flex align-items-center">
                    <!-- connect button -->
                    <a href="#" class="btn btn-primary" v-if="authStore.user.is_strava_linked == 0" @click="submitConnectStrava">{{ $t("settingsIntegrationsZone.buttonConnect") }}</a>

                    <!-- retrieve activities and other buttons -->
                    <div class="dropdown" v-else>
                        <button class="btn btn-secondary dropdown-toggle" type="button" data-bs-toggle="dropdown" aria-expanded="false">
                            {{ $t("settingsIntegrationsZone.buttonDropdownOptions") }}
                        </button>
                        <ul class="dropdown-menu">
                            <li>
                                <!-- retrieve strava activities by days -->
                                <a class="dropdown-item" href="#" role="button" data-bs-toggle="modal" data-bs-target="#retrieveStravaActivitiesByDaysModal">{{ $t("settingsIntegrationsZone.modalRetrieveActivitiesByDaysTitle") }}</a>
                            </li>
                            <li>
                                <!-- retrieve gear -->
                                <a href="#" class="dropdown-item" @click="submitRetrieveStravaGear">{{ $t("settingsIntegrationsZone.buttonStravaRetrieveGear") }}</a>
                            </li>
                            <li>
                                <!-- unlink Strava -->
                                <a href="#" class="dropdown-item" role="button" data-bs-toggle="modal" data-bs-target="#unlinkStravaModal">{{ $t("settingsIntegrationsZone.buttonStravaUnlink") }}</a>
                            </li>
                        </ul>
                    </div>
                </div>
            </li>
            <!-- bulk import zone -->
            <li class="list-group-item d-flex justify-content-between">
                <div class="d-flex align-items-center">
                    <font-awesome-icon :icon="['fas', 'file-import']" size="2x" />
                    <div class="ms-3">
                        <div class="fw-bold">
                            {{ $t("settingsIntegrationsZone.bulkImportIntegrationTitle") }}
                        </div>
                        {{ $t("settingsIntegrationsZone.bulkImportIntegrationBody") }}
                    </div>
                </div>
                <div class="d-flex align-items-center">
                    <!-- import button -->
                    <a href="#" class="btn btn-primary" role="button" @click="submitBulkImport">{{ $t("settingsIntegrationsZone.buttonBulkImport") }}</a>
                </div>
            </li>
			<!-- Garmin Connect zone -->
			<li class="list-group-item d-flex justify-content-between">
                <div class="d-flex align-items-center">
                    <!--<font-awesome-icon :icon="['fas', 'file-import']" size="2x" />-->
					<img src="/src/assets/garminconnect/Garmin_Connect_app_1024x1024-02.png" alt="Garmin Connect logo" height="32" />
                    <div class="ms-3">
                        <div class="fw-bold">
                            {{ $t("settingsIntegrationsZone.garminConnectIntegrationTitle") }}
                        </div>
                        {{ $t("settingsIntegrationsZone.garminConnectIntegrationBody") }}
                    </div>
                </div>
                <div class="d-flex align-items-center">
                    <!-- connect button -->
                    <a href="#" class="btn btn-primary" v-if="authStore.user.is_garminconnect_linked == 0" data-bs-toggle="modal" data-bs-target="#garminConnectAuthModal">{{ $t("settingsIntegrationsZone.buttonConnect") }}</a>

                    <!-- retrieve activities and other buttons -->
                    <div class="dropdown" v-else>
                        <button class="btn btn-secondary dropdown-toggle" type="button" data-bs-toggle="dropdown" aria-expanded="false">
                            {{ $t("settingsIntegrationsZone.buttonDropdownOptions") }}
                        </button>
                        <ul class="dropdown-menu">
							<li>
								<!-- retrieve garmin connect activities by days -->
								<a class="dropdown-item" href="#" role="button" data-bs-toggle="modal" data-bs-target="#retrieveGarminConnectActivitiesByDaysModal">{{ $t("settingsIntegrationsZone.modalRetrieveActivitiesByDaysTitle") }}</a>
							</li>
						</ul>
					</div>
                </div>
            </li>
        </ul>

		<!-- modal garmin connect auth -->
		<GarminConnectLoginModalComponent />

        <!-- modal retrieve strava activities by days -->
        <div class="modal fade" id="retrieveStravaActivitiesByDaysModal" tabindex="-1" aria-labelledby="retrieveStravaActivitiesByDaysModalLabel" aria-hidden="true">
            <div class="modal-dialog">
                <div class="modal-content">
                    <div class="modal-header">
                        <h1 class="modal-title fs-5" id="retrieveStravaActivitiesByDaysModalLabel">{{ $t("settingsIntegrationsZone.modalRetrieveActivitiesByDaysTitle") }}</h1>
                        <button type="button" class="btn-close" data-bs-dismiss="modal" aria-label="Close"></button>
                    </div>
                    <form @submit.prevent="submitRetrieveStravaActivities">
                        <div class="modal-body">
                                <!-- number of days fields -->
                                <label for="daysToRetrieve"><b>* {{ $t("settingsIntegrationsZone.modalRetrieveActivitiesByDaysLabel") }}</b></label>
                                <input class="form-control" type="number" name="daysToRetrieve" :placeholder='$t("settingsIntegrationsZone.modalRetrieveActivitiesByDaysPlaceholder")' v-model="daysToRetrieveStrava" required>
                        </div>
                        <div class="modal-footer">
                            <button type="button" class="btn btn-secondary" name="retrieveStravaActivities" data-bs-dismiss="modal">{{ $t("generalItems.buttonClose") }}</button>
                            <button type="submit" class="btn btn-success" data-bs-dismiss="modal">{{ $t("settingsIntegrationsZone.modalRetrieveButton") }}</button>
                        </div>
                    </form>
                </div>
            </div>
        </div>

		<!-- modal retrieve garmin connect activities by days -->
        <div class="modal fade" id="retrieveGarminConnectActivitiesByDaysModal" tabindex="-1" aria-labelledby="retrieveGarminConnectActivitiesByDaysModal" aria-hidden="true">
            <div class="modal-dialog">
                <div class="modal-content">
                    <div class="modal-header">
                        <h1 class="modal-title fs-5" id="retrieveGarminConnectActivitiesByDaysModal">{{ $t("settingsIntegrationsZone.modalRetrieveActivitiesByDaysTitle") }}</h1>
                        <button type="button" class="btn-close" data-bs-dismiss="modal" aria-label="Close"></button>
                    </div>
                    <form @submit.prevent="submitRetrieveGarminConnectActivities">
                        <div class="modal-body">
                                <!-- number of days fields -->
                                <label for="daysToRetrieve"><b>* {{ $t("settingsIntegrationsZone.modalRetrieveActivitiesByDaysLabel") }}</b></label>
                                <input class="form-control" type="number" name="daysToRetrieve" :placeholder='$t("settingsIntegrationsZone.modalRetrieveActivitiesByDaysPlaceholder")' v-model="daysToRetrieveGarmin" required>
                        </div>
                        <div class="modal-footer">
                            <button type="button" class="btn btn-secondary" name="retrieveStravaActivities" data-bs-dismiss="modal">{{ $t("generalItems.buttonClose") }}</button>
                            <button type="submit" class="btn btn-success" data-bs-dismiss="modal">{{ $t("settingsIntegrationsZone.modalRetrieveButton") }}</button>
                        </div>
                    </form>
                </div>
            </div>
        </div>

		<ModalComponent modalId="unlinkStravaModal" :title="t('settingsIntegrationsZone.modalUnlinkStravaTitle')" :body="`${t('settingsIntegrationsZone.modalUnlinkStravaBody')}`" :actionButtonType="`danger`" :actionButtonText="t('settingsIntegrationsZone.modalUnlinkStravaTitle')" @submitAction="buttonStravaUnlink"/>
    </div>
</template>

<script>
import { ref } from "vue";
import { useI18n } from "vue-i18n";
// Import Notivue push
import { push } from "notivue";
// Importing the stores
import { useAuthStore } from "@/stores/authStore";
// Importing the services
import { strava } from "@/services/stravaService";
import { activities } from "@/services/activitiesService";
import { garminConnect } from "@/services/garminConnectService";
// Import the components
import ModalComponent from "@/components/Modals/ModalComponent.vue";
import GarminConnectLoginModalComponent from "./SettingsIntegrations/GarminConnectLoginModalComponent.vue";

//import Modal from 'bootstrap/js/dist/modal';

export default {
	components: {
		ModalComponent,
		GarminConnectLoginModalComponent,
	},
	setup() {
		const authStore = useAuthStore();
		const { locale, t } = useI18n();
		const daysToRetrieveStrava = ref(7);
		const daysToRetrieveGarmin = ref(7);
		const garminConnectUsername = ref("");
		const garminConnectPassword = ref("");

		async function submitConnectStrava() {
			const array = new Uint8Array(16);
			window.crypto.getRandomValues(array);
			const state = Array.from(array, (byte) =>
				byte.toString(16).padStart(2, "0"),
			).join("");

			try {
				await strava.setUniqueUserStateStravaLink(state);

				strava.linkStrava(state);
			} catch (error) {
				// If there is an error, show the error alert.
				push.error(
					`${t("settingsIntegrationsZone.errorMessageUnableToLinkStrava")} - ${error}`,
				);
			}
		}

		async function submitRetrieveStravaActivities() {
			try {
				await strava.getStravaActivitiesLastDays(daysToRetrieveStrava.value);

				// Show the loading alert.
				push.info(
					t(
						"settingsIntegrationsZone.loadingMessageRetrievingStravaActivities",
					),
				);
			} catch (error) {
				// If there is an error, show the error alert.
				push.error(
					`${t("settingsIntegrationsZone.errorMessageUnableToGetStravaActivities")} - ${error}`,
				);
			}
		}

		async function submitRetrieveStravaGear() {
			try {
				await strava.getStravaGear();

				// Show the loading alert.
				push.success(
					t("settingsIntegrationsZone.loadingMessageRetrievingStravaGear"),
				);
			} catch (error) {
				// If there is an error, show the error alert.
				push.error(
					`${t("settingsIntegrationsZone.errorMessageUnableToGetStravaGear")} - ${error}`,
				);
			}
		}

		async function buttonStravaUnlink() {
            // Set the loading message
            const notification = push.promise(t('settingsIntegrationsZone.processingMessageUnlinkStrava'));
			try {
				await strava.unlinkStrava();

				// Set the user object with the is_strava_linked property set to 0.
                const user = authStore.user;
                user.is_strava_linked = 0;
                authStore.setUser(user, locale);

				// Show the success alert.
				notification.resolve(t("settingsIntegrationsZone.successMessageStravaUnlinked"));
			} catch (error) {
				// If there is an error, show the error alert.
				notification.reject(
					`${t("settingsIntegrationsZone.errorMessageUnableToUnlinkStrava")} - ${error}`,
				);
			}
		}

		async function submitBulkImport() {
			try {
				await activities.bulkImportActivities();

				// Show the loading alert.
				push.info(t("settingsIntegrationsZone.loadingMessageBulkImport"));
			} catch (error) {
				// If there is an error, show the error alert.
				push.error(
					`${t("settingsIntegrationsZone.errorMessageUnableToImportActivities")} - ${error}`,
				);
			}
		}

		async function submitRetrieveGarminConnectActivities() {
			try {
				await garminConnect.getGarminConnectActivitiesLastDays(daysToRetrieveGarmin.value);

				// Show the loading alert.
				push.info(
					t(
						"settingsIntegrationsZone.loadingMessageRetrievingGarminConnectActivities",
					),
				);
			} catch (error) {
				// If there is an error, show the error alert.
				push.error(
					`${t("settingsIntegrationsZone.errorMessageUnableToGetGarminConnectActivities")} - ${error}`,
				);
			}
		}

		return {
			authStore,
			t,
			submitConnectStrava,
			submitRetrieveStravaActivities,
			daysToRetrieveStrava,
			submitRetrieveStravaGear,
			buttonStravaUnlink,
			submitBulkImport,
			garminConnectUsername,
			garminConnectPassword,
			submitRetrieveGarminConnectActivities,
			daysToRetrieveGarmin,
		};
	},
};
</script>