<template>
    <div class="col">
        <form>
            <!-- Units -->
            <label for="serverSettingsUnits" class="form-label">{{ $t("settingsServerSettingsZoneComponent.unitsLabel") }}</label>
            <select class="form-select" name="serverSettingsUnits" v-model="units" required>
                <option value="1">{{ $t("settingsServerSettingsZoneComponent.unitsMetric") }}</option>
                <option value="2">{{ $t("settingsServerSettingsZoneComponent.unitsImperial") }}</option>
            </select>
            <!-- Public shareable links -->
            <label class="mt-2 form-label" for="serverSettingsPublicShareableLinks">{{ $t("settingsServerSettingsZoneComponent.publicShareableLinksLabel") }}</label>
            <select class="form-select" name="serverSettingsPublicShareableLinks" v-model="publicShareableLinks" required>
                <option value="false">{{ $t("settingsServerSettingsZoneComponent.publicShareableLinksFalse") }}</option>
                <option value="true">{{ $t("settingsServerSettingsZoneComponent.publicShareableLinksTrue") }}</option>
            </select>
        </form>
    </div>
</template>

<script>
import { ref, onMounted, watch, computed } from "vue";
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

        async function updateServerSettings() {
            const data = {
                id: 1,
                units: units.value,
                public_shareable_links: publicShareableLinks.value,
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
        watch(units, updateServerSettings, { immediate: false });
        watch(publicShareableLinks, updateServerSettings, { immediate: false });

        return {
			t,
			isLoading,
            units,
            publicShareableLinks,
		};
	},
};
</script>