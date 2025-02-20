<template>
    <div class="col">
        <form class="bg-body-tertiary rounded p-3">
            <!-- Units -->
            <h4>{{ $t("settingsServerSettingsZoneComponent.unitsLabel") }}</h4>
            <select class="form-select" name="serverSettingsUnits" v-model="units" required>
                <option value="1">{{ $t("settingsServerSettingsZoneComponent.unitsMetric") }}</option>
                <option value="2">{{ $t("settingsServerSettingsZoneComponent.unitsImperial") }}</option>
            </select>
            <hr>
            <!-- Public shareable links -->
            <h4 class="mt-4">{{ $t("settingsServerSettingsZoneComponent.publicShareableLinksLabel") }}</h4>
            <label class="form-label" for="serverSettingsPublicShareableLinksEnabledSelect">{{ $t("settingsServerSettingsZoneComponent.publicShareableLinksEnabledLabel") }}</label>
            <select class="form-select" name="serverSettingsPublicShareableLinksEnabledSelect" v-model="publicShareableLinks" required>
                <option value="false">{{ $t("settingsServerSettingsZoneComponent.publicShareableLinksFalse") }}</option>
                <option value="true">{{ $t("settingsServerSettingsZoneComponent.publicShareableLinksTrue") }}</option>
            </select>
            <div class="alert alert-warning mt-2" role="alert">
                <font-awesome-icon :icon="['fas', 'triangle-exclamation']" />
                <span class="ms-2">{{ $t("settingsServerSettingsZoneComponent.serverSettingsPublicShareableLinksEnabledWarningAlert") }}</span>
            </div>
            <!-- Public shareable user info -->
            <label class="form-label" for="serverSettingsPublicShareableLinksShowUserInfo">{{ $t("settingsServerSettingsZoneComponent.publicShareableLinksShowUserInfoLabel") }}</label>
            <select class="form-select" name="serverSettingsPublicShareableLinksShowUserInfo" v-model="publicShareableLinksUserInfo" required>
                <option value="false">{{ $t("settingsServerSettingsZoneComponent.publicShareableLinksFalse") }}</option>
                <option value="true">{{ $t("settingsServerSettingsZoneComponent.publicShareableLinksTrue") }}</option>
            </select>
            <div class="alert alert-warning mt-2" role="alert">
                <font-awesome-icon :icon="['fas', 'triangle-exclamation']" />
                <span class="ms-2">{{ $t("settingsServerSettingsZoneComponent.serverSettingsPublicShareableLinksShowUserWarningAlert") }}</span>
            </div>
        </form>
    </div>
</template>

<script>
import { ref, watch } from "vue";
import { useI18n } from "vue-i18n";
// Import stores
import { useServerSettingsStore } from "@/stores/serverSettingsStore";
// Import services
import { serverSettings } from "@/services/serverSettingsService";
// Import Notivue push
import { push } from "notivue";
// Importing the components
import LoadingComponent from "@/components/GeneralComponents/LoadingComponent.vue";
import NoItemsFoundComponent from "@/components/GeneralComponents/NoItemsFoundComponents.vue";
import UsersListComponent from "@/components/Settings/SettingsUsersZone/UsersListComponent.vue";
import PaginationComponent from "@/components/GeneralComponents/PaginationComponent.vue";
import UsersAddEditUserModalComponent from "@/components/Settings/SettingsUsersZone/UsersAddEditUserModalComponent.vue";

export default {
	components: {
		LoadingComponent,
		NoItemsFoundComponent,
		PaginationComponent,
		UsersListComponent,
		UsersAddEditUserModalComponent,
	},
	setup() {
		const { t } = useI18n();
		const isLoading = ref(true);
        const serverSettingsStore = useServerSettingsStore();
        const units = ref(serverSettingsStore.serverSettings.units);
        const publicShareableLinks = ref(serverSettingsStore.serverSettings.public_shareable_links);
        const publicShareableLinksUserInfo = ref(serverSettingsStore.serverSettings.public_shareable_links_user_info);

        async function updateServerSettings() {
            const data = {
                id: 1,
                units: units.value,
                public_shareable_links: publicShareableLinks.value,
                public_shareable_links_user_info: publicShareableLinksUserInfo.value,
            };
            try {
                // Update the server settings in the DB
                await serverSettings.editServerSettings(data);

                // Update the server settings in the store
                serverSettingsStore.setServerSettings(data);

                push.success(t("settingsServerSettingsZoneComponent.successUpdateServerSettings"));
            } catch (error) {
                push.error(t("settingsServerSettingsZoneComponent.errorUpdateServerSettings"));
            }
        }

        // watchers
        watch([units, publicShareableLinks, publicShareableLinksUserInfo], async () => {
            await updateServerSettings();
        }, { immediate: false });

        return {
			t,
			isLoading,
            units,
            publicShareableLinks,
            publicShareableLinksUserInfo,
		};
	},
};
</script>