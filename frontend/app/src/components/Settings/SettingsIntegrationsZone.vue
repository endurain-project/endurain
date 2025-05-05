<template>
    <div class="col">
		<div class="bg-body-tertiary rounded p-3 shadow-sm">
			<!-- list zone -->
			<ul class="list-group list-group-flush">
				<!-- strava zone -->
				<li class="list-group-item d-flex justify-content-between bg-body-tertiary px-0 pt-0">
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
						<a href="#" class="btn btn-primary" role="button" data-bs-toggle="modal" data-bs-target="#retrieveStravaClientIdModal" v-if="authStore.user.is_strava_linked == 0">{{ $t("settingsIntegrationsZone.buttonConnect") }}</a>

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
									<a href="#" class="dropdown-item" @click="submitRetrieveStravaGear">{{ $t("settingsIntegrationsZone.buttonRetrieveGear") }}</a>
								</li>
								<li><hr class="dropdown-divider"></li>
								<li>
									<!-- relink Strava -->
									<a href="#" class="dropdown-item" role="button" @click="submitConnectStrava">{{ $t("settingsIntegrationsZone.buttonRelink") }}</a>
								</li>
								<li><hr class="dropdown-divider"></li>
								<li>
									<!-- unlink Strava -->
									<a href="#" class="dropdown-item" role="button" data-bs-toggle="modal" data-bs-target="#unlinkStravaModal">{{ $t("settingsIntegrationsZone.buttonUnlink") }}</a>
								</li>
							</ul>
						</div>
					</div>
				</li>
				<!-- bulk import zone -->
				<li class="list-group-item d-flex justify-content-between bg-body-tertiary px-0">
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
				<li class="list-group-item d-flex justify-content-between bg-body-tertiary px-0 pb-0">
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
								<li>
									<!-- retrieve gear -->
									<a href="#" class="dropdown-item" @click="submitRetrieveGarminConnectGear">{{ $t("settingsIntegrationsZone.buttonRetrieveGear") }}</a>
								</li>
								<li>
									<!-- retrieve garmin connect health data by days -->
									<a class="dropdown-item" href="#" role="button" data-bs-toggle="modal" data-bs-target="#retrieveGarminConnectHealthDataByDaysModal">{{ $t("settingsIntegrationsZone.modalRetrieveHealthDataByDaysTitle") }}</a>
								</li>
								<li><hr class="dropdown-divider"></li>
								<li>
									<!-- unlink Garmin Connect -->
									<a href="#" class="dropdown-item" role="button" data-bs-toggle="modal" data-bs-target="#unlinkGarminConnectModal">{{ $t("settingsIntegrationsZone.buttonUnlink") }}</a>
								</li>
							</ul>
						</div>
					</div>
				</li>
			</ul>

			<!-- modal retrieve Strava Client ID -->
			<ModalComponentNumberAndStringInput modalId="retrieveStravaClientIdModal" :title="t('settingsIntegrationsZone.modalRetrieveClientIdTitle')" :numberFieldLabel="`${t('settingsIntegrationsZone.modalRetrieveClientIdLabel')}`" :numberDefaultValue="Number(123456)" :stringFieldLabel="`${t('settingsIntegrationsZone.modalRetrieveClientSecretLabel')}`" :actionButtonType="`success`" :actionButtonText="t('settingsIntegrationsZone.buttonConnect')" @fieldsToEmitAction="submitConnectStrava"/>

			<!-- modal retrieve Strava activities by days -->
			<ModalComponentNumberInput modalId="retrieveStravaActivitiesByDaysModal" :title="t('settingsIntegrationsZone.modalRetrieveActivitiesByDaysTitle')" :numberFieldLabel="`${t('settingsIntegrationsZone.modalRetrieveActivitiesByDaysLabel')}`" :actionButtonType="`success`" :actionButtonText="t('settingsIntegrationsZone.modalRetrieveButton')" @numberToEmitAction="submitRetrieveStravaActivities"/>

			<!-- modal unlink Strava -->
			<ModalComponent modalId="unlinkStravaModal" :title="t('settingsIntegrationsZone.modalUnlinkStravaTitle')" :body="`${t('settingsIntegrationsZone.modalUnlinkStravaBody')}`" :actionButtonType="`danger`" :actionButtonText="t('settingsIntegrationsZone.modalUnlinkStravaTitle')" @submitAction="buttonStravaUnlink"/>

			<!-- modal garmin connect auth -->
			<GarminConnectLoginModalComponent />

			<!-- modal retrieve Garmin Connect activities by days -->
			<ModalComponentNumberInput modalId="retrieveGarminConnectActivitiesByDaysModal" :title="t('settingsIntegrationsZone.modalRetrieveActivitiesByDaysTitle')" :numberFieldLabel="`${t('settingsIntegrationsZone.modalRetrieveActivitiesByDaysLabel')}`" :actionButtonType="`success`" :actionButtonText="t('settingsIntegrationsZone.modalRetrieveButton')" @numberToEmitAction="submitRetrieveGarminConnectActivities"/>

			<!-- modal retrieve Garmin Connect health data by days -->
			<ModalComponentNumberInput modalId="retrieveGarminConnectHealthDataByDaysModal" :title="t('settingsIntegrationsZone.modalRetrieveHealthDataByDaysTitle')" :numberFieldLabel="`${t('settingsIntegrationsZone.modalRetrieveActivitiesByDaysLabel')}`" :actionButtonType="`success`" :actionButtonText="t('settingsIntegrationsZone.modalRetrieveButton')" @numberToEmitAction="submitRetrieveGarminConnectHealthData"/>

			<!-- modal unlink Garmin Connect -->
			<ModalComponent modalId="unlinkGarminConnectModal" :title="t('settingsIntegrationsZone.modalUnlinkGarminConnectTitle')" :body="`${t('settingsIntegrationsZone.modalUnlinkGarminConnectBody')}`" :actionButtonType="`danger`" :actionButtonText="t('settingsIntegrationsZone.modalUnlinkGarminConnectTitle')" @submitAction="buttonGarminConnectUnlink"/>
		</div>
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
import ModalComponentNumberAndStringInput from "@/components/Modals/ModalComponentNumberAndStringInput.vue";
import ModalComponentNumberInput from "@/components/Modals/ModalComponentNumberInput.vue";
import GarminConnectLoginModalComponent from "./SettingsIntegrations/GarminConnectLoginModalComponent.vue";

//import Modal from 'bootstrap/js/dist/modal';

export default {
	components: {
		ModalComponent,
		ModalComponentNumberAndStringInput,
		ModalComponentNumberInput,
		GarminConnectLoginModalComponent,
	},
	setup() {
		const authStore = useAuthStore();
		const { locale, t } = useI18n();

		async function submitConnectStrava(stravaClient) {
			const array = new Uint8Array(16);
			window.crypto.getRandomValues(array);
			const state = Array.from(array, (byte) =>
				byte.toString(16).padStart(2, "0"),
			).join("");

			try {
				await strava.setUniqueUserStateStravaLink(state);
				await strava.setUserStravaClientSettings(stravaClient.numberToEmit, stravaClient.stringToEmit);

				strava.linkStrava(state, stravaClient.numberToEmit);
			} catch (error) {
				// If there is an error, show the error alert.
				push.error(
					`${t("settingsIntegrationsZone.errorMessageUnableToLinkStrava")} - ${error}`,
				);

				try {
					await strava.setUniqueUserStateStravaLink(null);
					await strava.setUserStravaClientSettings(null, null);
				} catch (error) {
					// If there is an error, show the error alert.
					push.error(
						`${t("settingsIntegrationsZone.errorMessageUnableToUnsetStravaClientSettings")} - ${error}`,
					);
				}
			} finally {
				// Clear the stravaClientId and stravaClientSecret fields
				stravaClient.numberToEmit = null;
				stravaClient.stringToEmit = null;
			}
		}

		async function submitRetrieveStravaActivities(daysToRetrieveStrava) {
			try {
				await strava.getStravaActivitiesLastDays(daysToRetrieveStrava);

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
				push.info(
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

		async function submitRetrieveGarminConnectActivities(daysToRetrieveGarmin) {
			try {
				await garminConnect.getGarminConnectActivitiesLastDays(daysToRetrieveGarmin);

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

		async function submitRetrieveGarminConnectGear() {
			try {
				await garminConnect.getGarminConnectGear();

				// Show the loading alert.
				push.info(
					t("settingsIntegrationsZone.loadingMessageRetrievingGarminConnectGear"),
				);
			} catch (error) {
				// If there is an error, show the error alert.
				push.error(
					`${t("settingsIntegrationsZone.errorMessageUnableToGetGarminConnectGear")} - ${error}`,
				);
			}
		}

		async function submitRetrieveGarminConnectHealthData(daysToRetrieveGarmin) {
			try {
				await garminConnect.getGarminConnectHealthDataLastDays(daysToRetrieveGarmin);

				// Show the loading alert.
				push.info(
					t("settingsIntegrationsZone.loadingMessageRetrievingGarminConnectHealthData"),
				);
			} catch (error) {
				// If there is an error, show the error alert.
				push.error(
					`${t("settingsIntegrationsZone.errorMessageUnableToGetGarminConnectHealthData")} - ${error}`,
				);
			}
		}

		async function buttonGarminConnectUnlink() {
			// Set the loading message
			const notification = push.promise(t('settingsIntegrationsZone.processingMessageUnlinkGarminConnect'));
			try {
				await garminConnect.unlinkGarminConnect();

				// Set the user object with the is_garminconnect_linked property set to 0.
				const user = authStore.user;
				user.is_garminconnect_linked = 0;
				authStore.setUser(user, locale);

				// Show the success alert.
				notification.resolve(t("settingsIntegrationsZone.successMessageGarminConnectUnlinked"));
			} catch (error) {
				// If there is an error, show the error alert.
				notification.reject(
					`${t("settingsIntegrationsZone.errorMessageUnableToUnlinkGarminConnect")} - ${error}`,
				);
			}
		}

		return {
			authStore,
			t,
			submitConnectStrava,
			submitRetrieveStravaActivities,
			submitRetrieveStravaGear,
			buttonStravaUnlink,
			submitBulkImport,
			submitRetrieveGarminConnectActivities,
			submitRetrieveGarminConnectGear,
			submitRetrieveGarminConnectHealthData,
			buttonGarminConnectUnlink,
		};
	},
};
</script>