<template>
    <div class="col">
        <p>Units {{ serverSettingsStore.serverSettings.units }}</p>
        <p>Public {{ serverSettingsStore.serverSettings.public_shareable_links }}</p>
    </div>
</template>

<script>
import { ref, onMounted, watch, computed } from "vue";
import { useI18n } from "vue-i18n";
// Import stores
import { useServerSettingsStore } from "@/stores/serverSettingsStore";
// Import Notivue push
import { push } from "notivue";
// import lodash
import { debounce } from "lodash";
// Importing the components
import LoadingComponent from "@/components/GeneralComponents/LoadingComponent.vue";
import NoItemsFoundComponent from "@/components/GeneralComponents/NoItemsFoundComponents.vue";
import UsersListComponent from "@/components/Settings/SettingsUsersZone/UsersListComponent.vue";
import PaginationComponent from "@/components/GeneralComponents/PaginationComponent.vue";
import UsersAddEditUserModalComponent from "@/components/Settings/SettingsUsersZone/UsersAddEditUserModalComponent.vue";
// Importing the services
import { users } from "@/services/usersService";

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

        return {
			t,
			isLoading,
            serverSettingsStore,
		};
	},
};
</script>