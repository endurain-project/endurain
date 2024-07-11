<template>
    <div class="col">
        <ErrorToastComponent v-if="errorMessage" />
        <SuccessToastComponent v-if="successMessage" />

        <div class="row row-gap-3 row-cols-sm-3 align-items-center">
            <div class="col">
                <div class="card text-center">
                    <img src="/src/assets/strava/api_logo_cptblWith_strava_stack_light.png" alt="Compatible with Strava image" class="card-img-top">
                    <div class="card-body">
                        <h4 class="card-title">{{ $t("settingsIntegrationsZone.stravaIntegrationTitle") }}</h4>
                        <p class="card-text">{{ $t("settingsIntegrationsZone.stravaIntegrationBody") }}</p>
                        <a href="#" class="btn btn-primary" :class="{ 'disabled': userMe.is_strava_linked == 1 }" @click="submitConnectStrava">{{ $t("settingsIntegrationsZone.buttonConnect") }}</a>
                        <div v-if="userMe.is_strava_linked == 1">
                            <hr>
                            <a href="#" class="btn btn-primary" @click="submitRetrieveStravaLastWeekActivities">{{ $t("settingsIntegrationsZone.buttonStravaRetrieveLastWeekActivities") }}</a>
                            <a href="#" class="btn btn-primary mt-3" @click="submitRetrieveStravaGear">{{ $t("settingsIntegrationsZone.buttonStravaRetrieveGear") }}</a>
                        </div>
                    </div>
                </div>
            </div>
        </div>
    </div>
</template>

<script>
import { ref } from 'vue';
import { useI18n } from 'vue-i18n';
// Importing the services
import { strava } from '@/services/strava';
// Importing the stores
import { useSuccessAlertStore } from '@/stores/Alerts/successAlert';
import { useErrorAlertStore } from '@/stores/Alerts/errorAlert';
import { useLoadingAlertStore } from '@/stores/Alerts/loadingAlert';
// Importing the components
import ErrorToastComponent from '@/components/Toasts/ErrorToastComponent.vue';
import SuccessToastComponent from '@/components/Toasts/SuccessToastComponent.vue';

import crypto from 'crypto';

export default {
    components: {
        ErrorToastComponent,
        SuccessToastComponent,
    },
    setup() {
        const userMe = JSON.parse(localStorage.getItem('userMe'));
        const { t } = useI18n();
        const errorAlertStore = useErrorAlertStore();
        const successAlertStore = useSuccessAlertStore();
        const loadingAlertStore = useLoadingAlertStore();
        const errorMessage = ref('');
        const successMessage = ref('');
        const loadingMessage = ref('');

        function resetMessageValues() {
            successMessage.value = '';
            successAlertStore.setAlertMessage(successMessage.value);
            errorMessage.value = '';
            errorAlertStore.setAlertMessage(errorMessage.value);
        }

        async function submitConnectStrava() {
            resetMessageValues();

            const state = crypto.randomBytes(16).toString('hex');

            try{
                await strava.setUniqueUserStateStravaLink(state);
                
                strava.linkStrava(state);
            } catch(error) {
                // If there is an error, set the error message and show the error alert.
                errorMessage.value = t('settingsIntegrationsZone.errorMessageUnableToLinkStrava') + " - " + error.toString();
                errorAlertStore.setAlertMessage(errorMessage.value);
            }
        }

        async function submitRetrieveStravaLastWeekActivities() {
            resetMessageValues();

            try {
                await strava.getStravaActivitiesLastDays(7);

                // Set the loading message and show the loading alert.
                loadingMessage.value = t('settingsIntegrationsZone.loadingMessageRetrievingStravaActivities');
                loadingAlertStore.setAlertMessage(loadingMessage.value);
                loadingAlertStore.setClosableState(true);
            } catch(error) {
                // If there is an error, set the error message and show the error alert.
                errorMessage.value = t('settingsIntegrationsZone.errorMessageUnableToGetStravaActivities') + " - " + error.toString();
                errorAlertStore.setAlertMessage(errorMessage.value);
            }
        }

        async function submitRetrieveStravaGear() {
            resetMessageValues();

            try {
                await strava.getStravaGear();

                // Set the loading message and show the loading alert.
                loadingMessage.value = t('settingsIntegrationsZone.loadingMessageRetrievingStravaGear');
                loadingAlertStore.setAlertMessage(loadingMessage.value);
                loadingAlertStore.setClosableState(true);
            } catch(error) {
                // If there is an error, set the error message and show the error alert.
                errorMessage.value = t('settingsIntegrationsZone.errorMessageUnableToGetStravaGear') + " - " + error.toString();
                errorAlertStore.setAlertMessage(errorMessage.value);
            }
        }

        return {
            userMe,
            t,
            errorMessage,
            successMessage,
            loadingMessage,
            submitConnectStrava,
            submitRetrieveStravaLastWeekActivities,
            submitRetrieveStravaGear,
        };
    },
};
</script>