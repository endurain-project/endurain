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
                                <a href="#" class="dropdown-item" @click="submitRetrieveStravaLastWeekActivities">{{ $t("settingsIntegrationsZone.buttonStravaRetrieveLastWeekActivities") }}</a>
                            </li>
                            <li>
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
    </div>
</template>

<script>
import { useI18n } from 'vue-i18n';
// Importing the utils
import { addToast } from '@/utils/toastUtils';
// Importing the stores
import { useAuthStore } from '@/stores/authStore';
// Importing the services
import { strava } from '@/services/stravaService';
import { activities }  from '@/services/activitiesService';

export default {
    components: {
        
    },
    setup() {
        const authStore = useAuthStore();
        const { t } = useI18n();

        async function submitConnectStrava() {
            const array = new Uint8Array(16);
            window.crypto.getRandomValues(array);
            const state = Array.from(array, byte => byte.toString(16).padStart(2, '0')).join('');

            try{
                await strava.setUniqueUserStateStravaLink(state);
                
                strava.linkStrava(state);
            } catch(error) {
                // If there is an error, set the error message and show the error alert.
                addToast(t('settingsIntegrationsZone.errorMessageUnableToLinkStrava') + " - " + error, 'danger', true);
            }
        }

        async function submitRetrieveStravaLastWeekActivities() {
            try {
                await strava.getStravaActivitiesLastDays(7);

                // Set the loading message and show the loading alert.
                addToast(t('settingsIntegrationsZone.loadingMessageRetrievingStravaActivities'), 'loading', true);
            } catch(error) {
                // If there is an error, set the error message and show the error alert.
                addToast(t('settingsIntegrationsZone.errorMessageUnableToGetStravaActivities') + " - " + error, 'danger', true);
            }
        }

        async function submitRetrieveStravaGear() {
            try {
                await strava.getStravaGear();

                // Set the loading message and show the loading alert.
                addToast(t('settingsIntegrationsZone.loadingMessageRetrievingStravaGear'), 'loading', true);
            } catch(error) {
                // If there is an error, set the error message and show the error alert.
                addToast(t('settingsIntegrationsZone.errorMessageUnableToGetStravaGear') + " - " + error, 'danger', true);
            }
        }

        async function submitBulkImport() {
            try {
                await activities.bulkImportActivities();

                // Set the loading message and show the loading alert.
                addToast(t('settingsIntegrationsZone.loadingMessageBulkImport'), 'loading', true);
            } catch(error) {
                // If there is an error, set the error message and show the error alert.
                addToast(t('settingsIntegrationsZone.errorMessageUnableToImportActivities') + " - " + error, 'danger', true);
            }
        }

        return {
            authStore,
            t,
            submitConnectStrava,
            submitRetrieveStravaLastWeekActivities,
            submitRetrieveStravaGear,
            submitBulkImport,
        };
    },
};
</script>