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
                                <a class="dropdown-item" href="#" role="button" data-bs-toggle="modal" data-bs-target="#retrieveStravaActivitiesByDaysModal">{{ $t("settingsIntegrationsZone.buttonStravaRetrieveActivitiesByDays") }}</a>
                            </li>
                            <li>
                                <!-- retrieve gear -->
                                <a href="#" class="dropdown-item" @click="submitRetrieveStravaGear">{{ $t("settingsIntegrationsZone.buttonStravaRetrieveGear") }}</a>
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
        </ul>

        <!-- modal retrieve strava activities by days -->
        <div class="modal fade" id="retrieveStravaActivitiesByDaysModal" tabindex="-1" aria-labelledby="retrieveStravaActivitiesByDaysModalLabel" aria-hidden="true">
            <div class="modal-dialog">
                <div class="modal-content">
                    <div class="modal-header">
                        <h1 class="modal-title fs-5" id="retrieveStravaActivitiesByDaysModalLabel">{{ $t("settingsIntegrationsZone.buttonStravaRetrieveActivitiesByDays") }}</h1>
                        <button type="button" class="btn-close" data-bs-dismiss="modal" aria-label="Close"></button>
                    </div>
                    <form @submit.prevent="submitRetrieveStravaActivities">
                        <div class="modal-body">
                                <!-- number of days fields -->
                                <label for="daysToRetrieve"><b>* {{ $t("settingsIntegrationsZone.modalRetrieveActivitiesByDaysLabel") }}</b></label>
                                <input class="form-control" type="number" name="daysToRetrieve" :placeholder='$t("settingsIntegrationsZone.modalRetrieveActivitiesByDaysPlaceholder")' v-model="daysToRetrieve" required>
                        </div>
                        <div class="modal-footer">
                            <button type="button" class="btn btn-secondary" name="retrieveStravaActivities" data-bs-dismiss="modal">{{ $t("generalItens.buttonClose") }}</button>
                            <button type="submit" class="btn btn-success" data-bs-dismiss="modal">{{ $t("settingsIntegrationsZone.modalRetrieveButton") }}</button>
                        </div>
                    </form>
                </div>
            </div>
        </div>
    </div>
</template>

<script>
import { ref } from 'vue';
import { useI18n } from 'vue-i18n';
// Importing the utils
import { addToast } from '@/utils/toastUtils';
// Importing the stores
import { useAuthStore } from '@/stores/authStore';
// Importing the services
import { strava } from '@/services/stravaService';
import { activities }  from '@/services/activitiesService';

//import Modal from 'bootstrap/js/dist/modal';


export default {
    components: {
        
    },
    setup() {
        const authStore = useAuthStore();
        const { t } = useI18n();
        const daysToRetrieve = ref(7);

        async function submitConnectStrava() {
            const array = new Uint8Array(16);
            window.crypto.getRandomValues(array);
            const state = Array.from(array, byte => byte.toString(16).padStart(2, '0')).join('');

            try{
                await strava.setUniqueUserStateStravaLink(state);
                
                strava.linkStrava(state);
            } catch(error) {
                // If there is an error, set the error message and show the error alert.
                addToast(`${t('settingsIntegrationsZone.errorMessageUnableToLinkStrava')} - ${error}`, 'danger', true);
            }
        }

        async function submitRetrieveStravaActivities() {
            try {
                await strava.getStravaActivitiesLastDays(daysToRetrieve.value);

                // Set the loading message and show the loading alert.
                addToast(t('settingsIntegrationsZone.loadingMessageRetrievingStravaActivities'), 'loading', true);

                // Ensure modal element and instance are correctly referenced
                //const myModalEl = document.getElementById('retrieveStravaActivitiesByDaysModal');
                //const myModal = Modal.getInstance(myModalEl) || new Modal(myModalEl); // Ensure an instance exists

                // Add the event listener for 'hidden.bs.modal' before hiding the modal
                //myModalEl.addEventListener('hidden.bs.modal', () => {
                //    myModal.dispose(); // Dispose of the modal instance when it is fully hidden
                //});

                // Hide the modal programmatically
                //myModal.hide();
            } catch(error) {
                // If there is an error, set the error message and show the error alert.
                addToast(`${t('settingsIntegrationsZone.errorMessageUnableToGetStravaActivities')} - ${error}`, 'danger', true);
            }
        }

        async function submitRetrieveStravaGear() {
            try {
                await strava.getStravaGear();

                // Set the loading message and show the loading alert.
                addToast(t('settingsIntegrationsZone.loadingMessageRetrievingStravaGear'), 'loading', true);
            } catch(error) {
                // If there is an error, set the error message and show the error alert.
                addToast(`${t('settingsIntegrationsZone.errorMessageUnableToGetStravaGear')} - ${error}`, 'danger', true);
            }
        }

        async function submitBulkImport() {
            try {
                await activities.bulkImportActivities();

                // Set the loading message and show the loading alert.
                addToast(t('settingsIntegrationsZone.loadingMessageBulkImport'), 'loading', true);
            } catch(error) {
                // If there is an error, set the error message and show the error alert.
                addToast(`${t('settingsIntegrationsZone.errorMessageUnableToImportActivities')} - ${error}`, 'danger', true);
            }
        }

        return {
            authStore,
            t,
            submitConnectStrava,
            submitRetrieveStravaActivities,
            daysToRetrieve,
            submitRetrieveStravaGear,
            submitBulkImport,
        };
    },
};
</script>