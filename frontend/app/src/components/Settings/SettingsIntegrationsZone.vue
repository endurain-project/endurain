<template>
    <div class="col">
        <div class="row row-gap-3 row-cols-sm-3 align-items-center">
            <div class="col">
                <div class="card text-center">
                    <img src="/src/assets/strava/api_logo_cptblWith_strava_stack_light.png" alt="Compatible with Strava image" class="card-img-top">
                    <div class="card-body">
                        <h4 class="card-title">{{ $t("settingsIntegrationsZone.stravaIntegrationTitle") }}</h4>
                        <p class="card-text">{{ $t("settingsIntegrationsZone.stravaIntegrationBody") }}</p>
                        <a href="#" class="btn btn-primary" :class="{ 'disabled': authStore.user.is_strava_linked == 1 }" @click="submitConnectStrava">{{ $t("settingsIntegrationsZone.buttonConnect") }}</a>
                        <div v-if="authStore.user.is_strava_linked == 1">
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
import { useI18n } from 'vue-i18n';
// Importing the utils
import { addToast } from '@/utils/toastUtils';
// Importing the stores
import { useAuthStore } from '@/stores/authStore';
// Importing the services
import { strava } from '@/services/strava';

import crypto from 'crypto';

export default {
    components: {
        
    },
    setup() {
        const authStore = useAuthStore();
        const { t } = useI18n();

        async function submitConnectStrava() {
            const state = crypto.randomBytes(16).toString('hex');

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

        return {
            authStore,
            t,
            submitConnectStrava,
            submitRetrieveStravaLastWeekActivities,
            submitRetrieveStravaGear,
        };
    },
};
</script>