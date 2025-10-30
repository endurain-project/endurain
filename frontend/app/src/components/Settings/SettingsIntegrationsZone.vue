<template>
  <div class="col">
    <div class="bg-body-tertiary rounded p-3 shadow-sm">
      <!-- list zone -->
      <ul class="list-group list-group-flush">
        <!-- strava zone -->
        <li class="list-group-item d-flex justify-content-between bg-body-tertiary px-0 pt-0">
          <div class="d-flex align-items-center">
            <font-awesome-icon class="me-2" :icon="['fab', 'strava']" size="2x" />
            <div class="ms-3">
              <div class="fw-bold">
                {{ $t('settingsIntegrationsZone.stravaIntegrationTitle') }}
              </div>
              {{ $t('settingsIntegrationsZone.stravaIntegrationBody') }}
            </div>
          </div>
          <div class="d-flex align-items-center">
            <!-- connect button -->
            <a
              href="#"
              class="btn btn-primary"
              role="button"
              data-bs-toggle="modal"
              data-bs-target="#retrieveStravaClientIdModal"
              v-if="authStore.user.is_strava_linked == 0"
              >{{ $t('settingsIntegrationsZone.buttonConnect') }}</a
            >

            <!-- retrieve activities and other buttons -->
            <div class="dropdown" v-else>
              <button
                class="btn btn-secondary dropdown-toggle"
                type="button"
                data-bs-toggle="dropdown"
                aria-expanded="false"
              >
                {{ $t('settingsIntegrationsZone.buttonDropdownOptions') }}
              </button>
              <ul class="dropdown-menu">
                <li>
                  <!-- retrieve strava activities by days -->
                  <a
                    class="dropdown-item"
                    href="#"
                    role="button"
                    data-bs-toggle="modal"
                    data-bs-target="#retrieveStravaActivitiesByDaysModal"
                    >{{ $t('settingsIntegrationsZone.modalRetrieveActivitiesByDaysTitle') }}</a
                  >
                </li>
                <li>
                  <!-- retrieve gear -->
                  <a href="#" class="dropdown-item" @click="submitRetrieveStravaGear">{{
                    $t('settingsIntegrationsZone.buttonRetrieveGear')
                  }}</a>
                </li>
                <li>
                  <hr class="dropdown-divider" />
                </li>
                <li>
                  <!-- relink Strava -->
                  <a
                    href="#"
                    class="dropdown-item"
                    role="button"
                    data-bs-toggle="modal"
                    data-bs-target="#retrieveStravaClientIdModal"
                    >{{ $t('settingsIntegrationsZone.buttonRelink') }}</a
                  >
                </li>
                <li>
                  <hr class="dropdown-divider" />
                </li>
                <li>
                  <!-- unlink Strava -->
                  <a
                    href="#"
                    class="dropdown-item"
                    role="button"
                    data-bs-toggle="modal"
                    data-bs-target="#unlinkStravaModal"
                    >{{ $t('settingsIntegrationsZone.buttonUnlink') }}</a
                  >
                </li>
              </ul>
            </div>
          </div>
        </li>
        <!-- Garmin Connect zone -->
        <li class="list-group-item d-flex justify-content-between bg-body-tertiary px-0 pb-0">
          <div class="d-flex align-items-center">
            <!--<font-awesome-icon :icon="['fas', 'file-import']" size="2x" />-->
            <img
              :src="INTEGRATION_LOGOS.garminConnectApp"
              alt="Garmin Connect logo"
              height="32"
            />
            <div class="ms-3">
              <div class="fw-bold">
                {{ $t('settingsIntegrationsZone.garminConnectIntegrationTitle') }}
              </div>
              {{ $t('settingsIntegrationsZone.garminConnectIntegrationBody') }}
            </div>
          </div>
          <div class="d-flex align-items-center">
            <!-- connect button -->
            <a
              href="#"
              class="btn btn-primary"
              v-if="authStore.user.is_garminconnect_linked == 0"
              data-bs-toggle="modal"
              data-bs-target="#garminConnectAuthModal"
              >{{ $t('settingsIntegrationsZone.buttonConnect') }}</a
            >

            <!-- retrieve activities and other buttons -->
            <div class="dropdown" v-else>
              <button
                class="btn btn-secondary dropdown-toggle"
                type="button"
                data-bs-toggle="dropdown"
                aria-expanded="false"
              >
                {{ $t('settingsIntegrationsZone.buttonDropdownOptions') }}
              </button>
              <ul class="dropdown-menu">
                <li>
                  <!-- retrieve garmin connect activities by days -->
                  <a
                    class="dropdown-item"
                    href="#"
                    role="button"
                    data-bs-toggle="modal"
                    data-bs-target="#retrieveGarminConnectActivitiesByDaysModal"
                    >{{ $t('settingsIntegrationsZone.modalRetrieveActivitiesByDaysTitle') }}</a
                  >
                </li>
                <li>
                  <!-- retrieve garmin connect activities by date range -->
                  <a
                    class="dropdown-item"
                    href="#"
                    role="button"
                    data-bs-toggle="modal"
                    data-bs-target="#retrieveGarminConnectActivitiesByDateRangeModal"
                    >{{ $t('settingsIntegrationsZone.modalRetrieveActivitiesByDateRangeTitle') }}</a
                  >
                </li>
                <li>
                  <hr class="dropdown-divider" />
                </li>
                <li>
                  <!-- retrieve gear -->
                  <a href="#" class="dropdown-item" @click="submitRetrieveGarminConnectGear">{{
                    $t('settingsIntegrationsZone.buttonRetrieveGear')
                  }}</a>
                </li>
                <li>
                  <hr class="dropdown-divider" />
                </li>
                <li>
                  <!-- retrieve garmin connect health data by days -->
                  <a
                    class="dropdown-item"
                    href="#"
                    role="button"
                    data-bs-toggle="modal"
                    data-bs-target="#retrieveGarminConnectHealthDataByDaysModal"
                    >{{ $t('settingsIntegrationsZone.modalRetrieveHealthDataByDaysTitle') }}</a
                  >
                </li>
                <li>
                  <!-- retrieve garmin connect health data by date range -->
                  <a
                    class="dropdown-item"
                    href="#"
                    role="button"
                    data-bs-toggle="modal"
                    data-bs-target="#retrieveGarminConnectHealthDataByDateRangeModal"
                    >{{ $t('settingsIntegrationsZone.modalRetrieveHealthDataByDateRangeTitle') }}</a
                  >
                </li>
                <li>
                  <hr class="dropdown-divider" />
                </li>
                <li>
                  <!-- unlink Garmin Connect -->
                  <a
                    href="#"
                    class="dropdown-item"
                    role="button"
                    data-bs-toggle="modal"
                    data-bs-target="#unlinkGarminConnectModal"
                    >{{ $t('settingsIntegrationsZone.buttonUnlink') }}</a
                  >
                </li>
              </ul>
            </div>
          </div>
        </li>
      </ul>

      <!-- modal retrieve Strava Client ID -->
      <ModalComponentNumberAndStringInput
        modalId="retrieveStravaClientIdModal"
        :title="t('settingsIntegrationsZone.modalRetrieveClientIdTitle')"
        :numberFieldLabel="`${t('settingsIntegrationsZone.modalRetrieveClientIdLabel')}`"
        :numberDefaultValue="Number(123456)"
        :stringFieldLabel="`${t('settingsIntegrationsZone.modalRetrieveClientSecretLabel')}`"
        :actionButtonType="`success`"
        :actionButtonText="t('settingsIntegrationsZone.buttonConnect')"
        @fieldsToEmitAction="submitConnectStrava"
      />

      <!-- modal retrieve Strava activities by days -->
      <ModalComponentNumberInput
        modalId="retrieveStravaActivitiesByDaysModal"
        :title="t('settingsIntegrationsZone.modalRetrieveActivitiesByDaysTitle')"
        :numberFieldLabel="`${t('settingsIntegrationsZone.modalRetrieveActivitiesByDaysLabel')}`"
        :actionButtonType="`success`"
        :actionButtonText="t('settingsIntegrationsZone.modalRetrieveButton')"
        @numberToEmitAction="submitRetrieveStravaActivities"
      />

      <!-- modal unlink Strava -->
      <ModalComponent
        modalId="unlinkStravaModal"
        :title="t('settingsIntegrationsZone.modalUnlinkStravaTitle')"
        :body="`${t('settingsIntegrationsZone.modalUnlinkStravaBody')}`"
        :actionButtonType="`danger`"
        :actionButtonText="t('settingsIntegrationsZone.modalUnlinkStravaTitle')"
        @submitAction="buttonStravaUnlink"
      />

      <!-- modal garmin connect auth -->
      <GarminConnectLoginModalComponent />

      <!-- modal retrieve Garmin Connect activities by days -->
      <ModalComponentNumberInput
        modalId="retrieveGarminConnectActivitiesByDaysModal"
        :title="t('settingsIntegrationsZone.modalRetrieveActivitiesByDaysTitle')"
        :numberFieldLabel="`${t('settingsIntegrationsZone.modalRetrieveActivitiesByDaysLabel')}`"
        :actionButtonType="`success`"
        :actionButtonText="t('settingsIntegrationsZone.modalRetrieveButton')"
        @numberToEmitAction="submitRetrieveGarminConnectActivitiesDays"
      />

      <!-- modal retrieve Garmin Connect activities by date range -->
      <ModalComponentDateRangeInput
        modalId="retrieveGarminConnectActivitiesByDateRangeModal"
        :title="t('settingsIntegrationsZone.modalRetrieveActivitiesByDateRangeTitle')"
        :actionButtonType="`success`"
        :actionButtonText="t('settingsIntegrationsZone.modalRetrieveButton')"
        @datesToEmitAction="submitRetrieveGarminConnectActivitiesDataRange"
      />

      <!-- modal retrieve Garmin Connect health data by days -->
      <ModalComponentNumberInput
        modalId="retrieveGarminConnectHealthDataByDaysModal"
        :title="t('settingsIntegrationsZone.modalRetrieveHealthDataByDaysTitle')"
        :numberFieldLabel="`${t('settingsIntegrationsZone.modalRetrieveActivitiesByDaysLabel')}`"
        :actionButtonType="`success`"
        :actionButtonText="t('settingsIntegrationsZone.modalRetrieveButton')"
        @numberToEmitAction="submitRetrieveGarminConnectHealthDataDays"
      />

      <!-- modal retrieve Garmin Connect health data by date range -->
      <ModalComponentDateRangeInput
        modalId="retrieveGarminConnectHealthDataByDateRangeModal"
        :title="t('settingsIntegrationsZone.modalRetrieveHealthDataByDateRangeTitle')"
        :actionButtonType="`success`"
        :actionButtonText="t('settingsIntegrationsZone.modalRetrieveButton')"
        @datesToEmitAction="submitRetrieveGarminConnectHealthDataDataRange"
      />

      <!-- modal unlink Garmin Connect -->
      <ModalComponent
        modalId="unlinkGarminConnectModal"
        :title="t('settingsIntegrationsZone.modalUnlinkGarminConnectTitle')"
        :body="`${t('settingsIntegrationsZone.modalUnlinkGarminConnectBody')}`"
        :actionButtonType="`danger`"
        :actionButtonText="t('settingsIntegrationsZone.modalUnlinkGarminConnectTitle')"
        @submitAction="buttonGarminConnectUnlink"
      />
    </div>
  </div>
</template>

<script setup>
import { useI18n } from 'vue-i18n'
import { push } from 'notivue'
import { useAuthStore } from '@/stores/authStore'
import { strava } from '@/services/stravaService'
import { activities } from '@/services/activitiesService'
import { garminConnect } from '@/services/garminConnectService'
import ModalComponent from '@/components/Modals/ModalComponent.vue'
import ModalComponentNumberAndStringInput from '@/components/Modals/ModalComponentNumberAndStringInput.vue'
import ModalComponentNumberInput from '@/components/Modals/ModalComponentNumberInput.vue'
import ModalComponentDateRangeInput from '@/components/Modals/ModalComponentDateRangeInput.vue'
import GarminConnectLoginModalComponent from './SettingsIntegrations/GarminConnectLoginModalComponent.vue'
import { INTEGRATION_LOGOS } from '@/constants/integrationLogoConstants'

const authStore = useAuthStore()
const { locale, t } = useI18n()

async function submitConnectStrava(stravaClient) {
  const array = new Uint8Array(16)
  window.crypto.getRandomValues(array)
  const state = Array.from(array, (byte) => byte.toString(16).padStart(2, '0')).join('')
  try {
    await strava.setUniqueUserStateStravaLink(state)
    await strava.setUserStravaClientSettings(stravaClient.numberToEmit, stravaClient.stringToEmit)
    strava.linkStrava(state, stravaClient.numberToEmit)
  } catch (error) {
    push.error(`${t('settingsIntegrationsZone.errorMessageUnableToLinkStrava')} - ${error}`)
    try {
      await strava.setUniqueUserStateStravaLink(null)
    } catch (error) {
      push.error(
        `${t('settingsIntegrationsZone.errorMessageUnableToUnsetStravaClientSettings')} - ${error}`
      )
    }
  } finally {
    stravaClient.numberToEmit = null
    stravaClient.stringToEmit = null
  }
}

async function submitRetrieveStravaActivities(daysToRetrieveStrava) {
  try {
    await strava.getStravaActivitiesLastDays(daysToRetrieveStrava)
    push.info(t('settingsIntegrationsZone.loadingMessageRetrievingStravaActivities'))
  } catch (error) {
    push.error(
      `${t('settingsIntegrationsZone.errorMessageUnableToGetStravaActivities')} - ${error}`
    )
  }
}

async function submitRetrieveStravaGear() {
  try {
    await strava.getStravaGear()
    push.info(t('settingsIntegrationsZone.loadingMessageRetrievingStravaGear'))
  } catch (error) {
    push.error(`${t('settingsIntegrationsZone.errorMessageUnableToGetStravaGear')} - ${error}`)
  }
}

async function buttonStravaUnlink() {
  const notification = push.promise(t('settingsIntegrationsZone.processingMessageUnlinkStrava'))
  try {
    await strava.unlinkStrava()
    const user = authStore.user
    user.is_strava_linked = 0
    authStore.setUser(user, locale)
    notification.resolve(t('settingsIntegrationsZone.successMessageStravaUnlinked'))
  } catch (error) {
    notification.reject(
      `${t('settingsIntegrationsZone.errorMessageUnableToUnlinkStrava')} - ${error}`
    )
  }
}

async function submitRetrieveGarminConnectActivitiesDays(days) {
  try {
    const endDate = new Date()
    const startDate = new Date()
    startDate.setDate(endDate.getDate() - days)
    const formattedStartDate = startDate.toISOString().split('T')[0]
    const formattedEndDate = endDate.toISOString().split('T')[0]
    await garminConnect.getGarminConnectActivitiesByDates(formattedStartDate, formattedEndDate)
    push.info(t('settingsIntegrationsZone.loadingMessageRetrievingGarminConnectActivities'))
  } catch (error) {
    push.error(
      `${t('settingsIntegrationsZone.errorMessageUnableToGetGarminConnectActivitiesDays')} - ${error}`
    )
  }
}

async function submitRetrieveGarminConnectActivitiesDataRange(dateRange) {
  try {
    await garminConnect.getGarminConnectActivitiesByDates(dateRange.startDate, dateRange.endDate)
    push.info(t('settingsIntegrationsZone.loadingMessageRetrievingGarminConnectActivities'))
  } catch (error) {
    push.error(
      `${t('settingsIntegrationsZone.errorMessageUnableToGetGarminConnectActivitiesDataRange')} - ${error}`
    )
  }
}

async function submitRetrieveGarminConnectGear() {
  try {
    await garminConnect.getGarminConnectGear()
    push.info(t('settingsIntegrationsZone.loadingMessageRetrievingGarminConnectGear'))
  } catch (error) {
    push.error(
      `${t('settingsIntegrationsZone.errorMessageUnableToGetGarminConnectGear')} - ${error}`
    )
  }
}

async function submitRetrieveGarminConnectHealthDataDataRange(dateRange) {
  try {
    await garminConnect.getGarminConnectHealthDataByDates(dateRange.startDate, dateRange.endDate)
    push.info(t('settingsIntegrationsZone.loadingMessageRetrievingGarminConnectHealthData'))
  } catch (error) {
    push.error(
      `${t('settingsIntegrationsZone.errorMessageUnableToGetGarminConnectHealthDataDateRange')} - ${error}`
    )
  }
}

async function submitRetrieveGarminConnectHealthDataDays(days) {
  try {
    const endDate = new Date()
    const startDate = new Date()
    startDate.setDate(endDate.getDate() - days)
    const formattedStartDate = startDate.toISOString().split('T')[0]
    const formattedEndDate = endDate.toISOString().split('T')[0]
    await garminConnect.getGarminConnectHealthDataByDates(formattedStartDate, formattedEndDate)
    push.info(t('settingsIntegrationsZone.loadingMessageRetrievingGarminConnectHealthData'))
  } catch (error) {
    push.error(
      `${t('settingsIntegrationsZone.errorMessageUnableToGetGarminConnectHealthDataDays')} - ${error}`
    )
  }
}

async function buttonGarminConnectUnlink() {
  const notification = push.promise(
    t('settingsIntegrationsZone.processingMessageUnlinkGarminConnect')
  )
  try {
    await garminConnect.unlinkGarminConnect()
    const user = authStore.user
    user.is_garminconnect_linked = 0
    authStore.setUser(user, locale)
    notification.resolve(t('settingsIntegrationsZone.successMessageGarminConnectUnlinked'))
  } catch (error) {
    notification.reject(
      `${t('settingsIntegrationsZone.errorMessageUnableToUnlinkGarminConnect')} - ${error}`
    )
  }
}
</script>
