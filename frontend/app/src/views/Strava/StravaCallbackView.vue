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
import { useRoute, useRouter } from "vue-router";
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
		const router = useRouter();
		const { t } = useI18n();

		onMounted(async () => {
			if (route.query.state && route.query.code && route.query.scope) {
				try {
					await strava.linkStravaCallback(
						route.query.state,
						route.query.code,
						route.query.scope,
					);

					router.push({
						path: "/settings",
						query: { stravaLinked: "1" },
					});
				} catch (error) {
					// If there is an error, show the error alert.
					push.error(
						`${t("settingsIntegrationsZone.errorMessageUnableToLinkStrava")} - ${error}`,
					);
					router.push({
						path: "/settings",
						query: { stravaLinked: "0" },
					});
				}
			}
		});
	},
};
</script>