<template>
    <div class="col">
        <form class="bg-body-tertiary rounded p-3 shadow-sm">
            <!-- Units -->
            <h4>{{ $t("settingsServerSettingsZoneComponent.unitsLabel") }}</h4>
            <select class="form-select" name="serverSettingsUnits" v-model="units" required>
                <option value="1">{{ $t("settingsServerSettingsZoneComponent.unitsMetric") }}</option>
                <option value="2">{{ $t("settingsServerSettingsZoneComponent.unitsImperial") }}</option>
            </select>
            <hr>
            <!-- Public shareable links -->
            <h4 class="mt-4">{{ $t("settingsServerSettingsZoneComponent.publicShareableLinksLabel") }}</h4>
            <label class="form-label" for="serverSettingsPublicShareableLinksEnabledSelect">{{
                $t("settingsServerSettingsZoneComponent.publicShareableLinksEnabledLabel") }}</label>
            <select class="form-select" name="serverSettingsPublicShareableLinksEnabledSelect"
                v-model="publicShareableLinks" required>
                <option value="false">{{ $t("settingsServerSettingsZoneComponent.publicShareableLinksFalse") }}</option>
                <option value="true">{{ $t("settingsServerSettingsZoneComponent.publicShareableLinksTrue") }}</option>
            </select>
            <div class="alert alert-warning mt-2" role="alert">
                <font-awesome-icon :icon="['fas', 'triangle-exclamation']" />
                <span class="ms-2">{{
                    $t("settingsServerSettingsZoneComponent.serverSettingsPublicShareableLinksEnabledWarningAlert")
                    }}</span>
            </div>
            <!-- Public shareable user info -->
            <label class="form-label" for="serverSettingsPublicShareableLinksShowUserInfo">{{
                $t("settingsServerSettingsZoneComponent.publicShareableLinksShowUserInfoLabel") }}</label>
            <select class="form-select" name="serverSettingsPublicShareableLinksShowUserInfo"
                v-model="publicShareableLinksUserInfo" required>
                <option value="false">{{ $t("settingsServerSettingsZoneComponent.publicShareableLinksFalse") }}</option>
                <option value="true">{{ $t("settingsServerSettingsZoneComponent.publicShareableLinksTrue") }}</option>
            </select>
            <div class="alert alert-warning mt-2" role="alert">
                <font-awesome-icon :icon="['fas', 'triangle-exclamation']" />
                <span class="ms-2">{{
                    $t("settingsServerSettingsZoneComponent.serverSettingsPublicShareableLinksShowUserWarningAlert")
                    }}</span>
            </div>
            <hr>
            <!-- Login photo set -->
            <h4 class="mt-4">{{ $t("settingsServerSettingsZoneComponent.photosLabel") }}</h4>
            <div class="row">
                <div class="col">
                    <label class="form-label" for="serverSettingsLoginPhotoLabel">{{
                        $t("settingsServerSettingsZoneComponent.loginPhotoLabel") }}</label>
                    <!-- add login photo button -->
                    <a class="w-100 btn btn-primary shadow-sm" href="#" role="button" data-bs-toggle="modal"
                        data-bs-target="#addLoginPhotoModal" v-if="!loginPhotoSet">
                        {{ $t("settingsServerSettingsZoneComponent.buttonAddPhoto") }}
                    </a>

                    <!-- Delete login photo section -->
                    <a class="w-100 btn btn-danger" href="#" role="button" data-bs-toggle="modal"
                        data-bs-target="#deleteLoginPhotoModal" v-else>{{
                            $t("settingsServerSettingsZoneComponent.buttonDeleteLoginPhoto") }}</a>

                    <!-- Modal add login photo -->
                    <ModalComponentUploadFile modalId="addLoginPhotoModal"
                        :title="$t('settingsServerSettingsZoneComponent.loginPhotoLabel')"
                        :fileFieldLabel="$t('settingsServerSettingsZoneComponent.logonPhotoAddLabel') + ' ' + $t('settingsServerSettingsZoneComponent.logonPhotoAddDetailsLabel')"
                        filesAccepted=".png" actionButtonType="success"
                        :actionButtonText="$t('settingsServerSettingsZoneComponent.loginPhotoLabel')"
                        @fileToEmitAction="submitUploadFileForm" />

                    <!-- Modal delete login photo -->
                    <ModalComponent modalId="deleteLoginPhotoModal"
                        :title="t('settingsServerSettingsZoneComponent.buttonDeleteLoginPhoto')"
                        :body="`${t('settingsServerSettingsZoneComponent.modalDeleteLoginPhotoBody')}`"
                        actionButtonType="danger"
                        :actionButtonText="t('settingsServerSettingsZoneComponent.buttonDeleteLoginPhoto')"
                        @submitAction="submitDeleteLoginPhoto" />
                </div>
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
import UsersAddEditUserModalComponent from "@/components/Settings/SettingsUsersZone/UsersAddEditUserModalComponent.vue";
import ModalComponent from "@/components/Modals/ModalComponent.vue";
import ModalComponentUploadFile from "@/components/Modals/ModalComponentUploadFile.vue"

export default {
    components: {
        LoadingComponent,
        NoItemsFoundComponent,
        UsersListComponent,
        UsersAddEditUserModalComponent,
        ModalComponent,
        ModalComponentUploadFile,
    },
    setup() {
        const { t } = useI18n();
        const isLoading = ref(true);
        const serverSettingsStore = useServerSettingsStore();
        const units = ref(serverSettingsStore.serverSettings.units);
        const publicShareableLinks = ref(serverSettingsStore.serverSettings.public_shareable_links);
        const publicShareableLinksUserInfo = ref(serverSettingsStore.serverSettings.public_shareable_links_user_info);
        const loginPhotoSet = ref(serverSettingsStore.serverSettings.login_photo_set);

        async function updateServerSettings() {
            const data = {
                id: 1,
                units: units.value,
                public_shareable_links: publicShareableLinks.value,
                public_shareable_links_user_info: publicShareableLinksUserInfo.value,
                login_photo_set: loginPhotoSet.value,
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

        const submitUploadFileForm = async (file) => {
            // Set the loading message
            const notification = push.promise(t("settingsServerSettingsZoneComponent.processingPhotoUpload"));

            // If there is a file, create the form data and upload the file
            if (file) {
                // Create the form data
                const formData = new FormData();
                formData.append("file", file);
                try {
                    // Upload the file
                    await serverSettings.uploadLoginPhotoFile(formData);
                    // Set the login photo set to true
                    loginPhotoSet.value = true;

                    // Update the server settings in the store and DB
                    await updateServerSettings();

                    // Set the success message
                    notification.resolve(t("settingsServerSettingsZoneComponent.successPhotoUpload"));
                } catch (error) {
                    // Set the error message
                    notification.reject(`${error}`);
                }
            }
        };

        const submitDeleteLoginPhoto = async () => {
            // Set the loading message
            const notification = push.promise(t("settingsServerSettingsZoneComponent.processingPhotoDelete"));

            try {
                // Delete the login photo
                await serverSettings.deleteLoginPhotoFile();
                // Set the login photo set to false
                loginPhotoSet.value = false;

                // Update the server settings in the store and DB
                await updateServerSettings();

                // Set the success message
                notification.resolve(t("settingsServerSettingsZoneComponent.successPhotoDelete"));
            } catch (error) {
                // Set the error message
                notification.reject(`${error}`);
            }
        };

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
            loginPhotoSet,
            submitUploadFileForm,
            submitDeleteLoginPhoto,
        };
    },
};
</script>