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
                {{ $t('settingsImportZone.bulkImportIntegrationTitle') }}
              </div>
              {{ $t('settingsImportZone.bulkImportIntegrationBody') }}
            </div>
          </div>
          <div class="d-flex align-items-center">
            <!-- import button -->
            <a href="#" class="btn btn-primary" role="button" @click="submitBulkImport"
              >{{ $t('settingsImportZone.buttonBulkImport') }}
            </a>
          </div>
        </li>
        <!-- Strava bulk-export import zone -->
        <li class="list-group-item d-flex justify-content-between bg-body-tertiary px-0">
          <div class="d-flex align-items-center">
            <font-awesome-icon :icon="['fas', 'file-import']" size="2x" />
            <div class="ms-3">
              <div class="fw-bold">
                {{ $t('settingsImportZone.stravaGearImportTitle') }}
                {{ $t('generalItems.betaTag') }}
              </div>
              {{ $t('settingsImportZone.stravaGearImportBody') }}
            </div>
          </div>
          <div class="d-flex align-items-center">
            <div class="dropdown">
              <a
                class="btn btn-secondary dropdown-toggle"
                href="#"
                role="button"
                data-bs-toggle="dropdown"
                aria-expanded="false"
              >
                {{ $t('settingsImportZone.importTitle') }}
              </a>

              <ul class="dropdown-menu">
                <li>
                  <a class="dropdown-item" @click="submitStravaBikesImport">{{
                    $t('settingsImportZone.stravaGearImportbuttonBikes')
                  }}</a>
                </li>
                <li>
                  <a class="dropdown-item" @click="submitStravaShoesImport">{{
                    $t('settingsImportZone.stravaImportbuttonShoes')
                  }}</a>
                </li>
              </ul>
            </div>
          </div>
        </li>
      </ul>
    </div>
  </div>
</template>

<script setup>
import { useI18n } from 'vue-i18n'
// Import Notivue push
import { push } from 'notivue'
// Importing the services
import { activities } from '@/services/activitiesService'
import { strava as stravaService } from '@/services/stravaService'

const { t } = useI18n()

async function submitBulkImport() {
  try {
    await activities.bulkImportActivities()
    // Show the loading alert.
    push.info(t('settingsImportZone.loadingMessageBulkImport'))
  } catch (error) {
    // If there is an error, show the error alert.
    push.error(`${t('settingsImportZone.errorMessageUnableToImportActivities')} - ${error}`)
  }
}
async function submitStravaBikesImport() {
  // Set the loading message
  const notification = push.promise(t('settingsImportZone.loadingMessageStravaBikesImport'))
  try {
    await stravaService.importBikes()
    // Resolve the loading message with a success message
    notification.resolve(t('settingsImportZone.successMessageStravaBikesImport'))
  } catch (error) {
    // Reject the loading message with an error message
    notification.reject(`${t('settingsImportZone.errorMessageUnableToImportBikes')} - ${error}`)
  }
}
async function submitStravaShoesImport() {
  // Set the loading message
  const notification = push.promise(t('settingsImportZone.loadingMessageStravaShoesImport'))
  try {
    await stravaService.importShoes()
    // Resolve the loading message with a success message
    notification.resolve(t('settingsImportZone.successMessageStravaShoesImport'))
  } catch (error) {
    // Reject the loading message with an error message
    notification.reject(`${t('settingsImportZone.errorMessageUnableToImportShoes')} - ${error}`)
  }
}
</script>
