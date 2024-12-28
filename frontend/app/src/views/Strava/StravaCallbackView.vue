<template>
    <div>
        <LoadingComponent />
    </div>
</template>

<script>
import { ref, onMounted } from "vue";
import { useI18n } from "vue-i18n";
// Import Notivue push
import { push } from "notivue";
// Import router
import { useRoute } from 'vue-router';
// Import the components
import LoadingComponent from "@/components/GeneralComponents/LoadingComponent.vue";
// Importing the services
import { strava } from "@/services/stravaService";

export default {
	components: {
		LoadingComponent,
	},
	setup() {
        const route = useRoute();
		const { t } = useI18n();
        //https://enduraindev.jvslab.pt/api/v1/strava/link?state=1ea095ec842dd64da1f9b4ca534737ff&code=91576d035c07ca216c654ceb9784da988326422c&scope=read,activity:read,activity:read_all,profile:read_all,read_all

        onMounted(async () => {
            console.log(route.query.state);
            console.log(route.query.code);
            console.log(route.query.scope);
            if (route.query.state && route.query.code && route.query.scope) {
                try {
                    await strava.linkStravaCallback(route.query.state, route.query.code, route.query.scope);

                    router.push({
						path: "/settings",
						query: { stravaLinked: "1" },
					});
                } catch (error) {
                    // If there is an error, show the error alert.
                    push.error(
                        `${t("settingsIntegrationsZone.errorMessageUnableToLinkStrava")} - ${error}`,
                    );
                }
            }
		});
	},
};
</script>