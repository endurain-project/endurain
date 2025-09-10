<template>
  <div class="col">
    <div class="bg-body-tertiary rounded p-3 shadow-sm">
      <!-- list zone -->
      <ul class="list-group list-group-flush">
        <!-- bulk import zone -->
        <li class="list-group-item d-flex justify-content-between bg-body-tertiary px-0">
          <div class="d-flex align-items-center">
            <font-awesome-icon :icon="['fas', 'file-import']" size="2x" />
            <div class="ms-3">
              <div class="fw-bold">
                {{ $t("settingsImportZone.bulkImportIntegrationTitle") }}
              </div>
            {{ $t("settingsImportZone.bulkImportIntegrationBody") }}
            </div>
          </div>
          <div class="d-flex align-items-center">
            <!-- import button -->
            <a 
              href="#" 
              class="btn btn-primary" 
              role="button" 
              @click="submitBulkImport">{{ $t("settingsImportZone.buttonBulkImport") }}
            </a>
          </div>
        </li>
        <!-- Strava bulk-export import zone -->
        <li class="list-group-item d-flex justify-content-between bg-body-tertiary px-0">
          <div class="d-flex align-items-center">
          <font-awesome-icon :icon="['fas', 'file-import']" size="2x" />
            <div class="ms-3">
              <div class="fw-bold">
                {{ $t("settingsImportZone.stravaGearImportTitle") }} 
                {{ $t('generalItems.betaTag') }}
              </div>
            {{ $t("settingsImportZone.stravaGearImportBody") }}
            </div>
          </div>
          <div class="d-flex align-items-center">
            <!-- import bikes button -->
            <a 
              href="#" 
              class="btn btn-primary" 
              role="button" 
              @click="submitStravaBikesImport">{{ $t("settingsImportZone.stravaGearImportbuttonBikes") }}
            </a>
          </div>
          <div class="d-flex align-items-center">
            <!-- import shoes button -->
            <a 
              href="#" 
              class="btn btn-primary" 
              role="button" 
              @click="submitStravaShoesImport">{{ $t("settingsImportZone.stravaImportbuttonShoes") }}
            </a>
          </div>
        </li>
      </ul>
    </div>
  </div>
</template>

<script setup>
import { ref } from "vue";
import { useI18n } from "vue-i18n";
// Import Notivue push
import { push } from "notivue";
// Importing the stores
import { useAuthStore } from "@/stores/authStore";
// Importing the services
import { activities } from "@/services/activitiesService";
import { gears } from "@/services/gearsService";
// Import the components
import ModalComponent from "@/components/Modals/ModalComponent.vue";
import ModalComponentNumberAndStringInput from "@/components/Modals/ModalComponentNumberAndStringInput.vue";
import ModalComponentNumberInput from "@/components/Modals/ModalComponentNumberInput.vue";
import ModalComponentDateRangeInput from "@/components/Modals/ModalComponentDateRangeInput.vue";
const authStore = useAuthStore();
const { locale, t } = useI18n();
async function submitBulkImport() {
	try {
		await activities.bulkImportActivities();
		// Show the loading alert.
		push.info(t("settingsImportZone.loadingMessageBulkImport"));
	} catch (error) {
		// If there is an error, show the error alert.
		push.error(
			`${t("settingsImportZone.errorMessageUnableToImportActivities")} - ${error}`,
		);
	}
}
async function submitStravaBikesImport() {
	try {
		await gears.stravaBikesImport();
		// Show the loading alert.
		push.info(t("settingsImportZone.loadingMessageStravaBikesImport"));
	} catch (error) {
		// If there is an error, show the error alert.
		push.error(
			`${t("settingsImportZone.errorMessageUnableToImportBikes")} - ${error}`,
		);
	}
}
async function submitStravaShoesImport() {
	try {
		await gears.stravaShoesImport();
		// Show the loading alert.
		push.info(t("settingsImportZone.loadingMessageStravaShoesImport"));
	} catch (error) {
		// If there is an error, show the error alert.
		push.error(
			`${t("settingsImportZone.errorMessageUnableToImportShoes")} - ${error}`,
		);
	}
}
</script>
