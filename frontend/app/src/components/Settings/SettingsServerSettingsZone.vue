<template>
  <div class="col">
    <form class="bg-body-tertiary rounded p-3 shadow-sm">
      <!-- Defaults -->
      <h4>{{ $t('settingsServerSettingsZoneComponent.defaultsTitle') }}</h4>
      <LoadingComponent v-if="isLoading" />
      <div v-else>
        <!-- Units -->
        <label>{{ $t('settingsServerSettingsZoneComponent.unitsLabel') }}</label>
        <select class="form-select" name="serverSettingsUnits" v-model="units" required>
          <option value="metric">
            {{ $t('settingsServerSettingsZoneComponent.unitsMetric') }}
          </option>
          <option value="imperial">
            {{ $t('settingsServerSettingsZoneComponent.unitsImperial') }}
          </option>
        </select>
        <!-- Currency -->
        <label class="mt-1">{{ $t('settingsServerSettingsZoneComponent.currencyLabel') }}</label>
        <select class="form-select" name="serverSettingsCurrency" v-model="currency" required>
          <option value="euro">{{ $t('generalItems.currencyEuro') }}</option>
          <option value="dollar">{{ $t('generalItems.currencyDollar') }}</option>
          <option value="pound">{{ $t('generalItems.currencyPound') }}</option>
        </select>
        <!-- Num records per list -->
        <label class="mt-1">{{ $t('settingsServerSettingsZoneComponent.numRecordsLabel') }}</label>
        <select
          class="form-select"
          name="serverSettingsNumRecordsPerPage"
          v-model="numRecordsPerPage"
          required
        >
          <option :value="5">5</option>
          <option :value="10">10</option>
          <option :value="25">25</option>
          <option :value="50">50</option>
          <option :value="100">100</option>
        </select>
      </div>
      <hr />

      <!-- Password policy -->
      <h4>{{ $t('settingsServerSettingsZoneComponent.passwordTitle') }}</h4>
      <LoadingComponent v-if="isLoading" />
      <div v-else>
        <!-- Password type -->
        <label>{{ $t('settingsServerSettingsZoneComponent.passwordTypeLabel') }}</label>
        <select
          class="form-select"
          name="serverSettingsPasswordType"
          v-model="passwordType"
          required
        >
          <option value="strict">
            {{ $t('settingsServerSettingsZoneComponent.passwordTypeStrict') }}
          </option>
          <option value="length_only">
            {{ $t('settingsServerSettingsZoneComponent.passwordTypeLengthOnly') }}
          </option>
        </select>
        <!-- Password length regular users -->
        <label class="form-label mt-2">{{
          $t('settingsServerSettingsZoneComponent.passwordLengthRegularUsersLabel')
        }}</label>
        <select
          class="form-select"
          name="serverSettingsPasswordLengthRegularUsersSelect"
          v-model="passwordLengthRegularUsers"
          required
        >
          <option v-for="n in 13" :key="n + 7" :value="n + 7">{{ n + 7 }}</option>
        </select>
        <!-- Password length admins -->
        <label class="form-label mt-2">{{
          $t('settingsServerSettingsZoneComponent.passwordLengthAdminsUsersLabel')
        }}</label>
        <select
          class="form-select"
          name="serverSettingsPasswordLengthAdminsSelect"
          v-model="passwordLengthAdminsUsers"
          required
        >
          <option v-for="n in 18" :key="n + 7" :value="n + 7">{{ n + 7 }}</option>
        </select>
      </div>
      <hr />

      <!-- Sign-up -->
      <h4>{{ $t('settingsServerSettingsZoneComponent.signupTitle') }}</h4>
      <LoadingComponent v-if="isLoading" />
      <div v-else>
        <label class="form-label" for="serverSettingsSignUpEnabledSelect">{{
          $t('settingsServerSettingsZoneComponent.enabledLabel')
        }}</label>
        <select
          class="form-select"
          name="serverSettingsSignUpEnabledSelect"
          v-model="signUp"
          required
        >
          <option :value="false">
            {{ $t('generalItems.false') }}
          </option>
          <option :value="true">
            {{ $t('generalItems.true') }}
          </option>
        </select>
        <!-- requires admin approval -->
        <label class="form-label" for="serverSettingsAdminApprovalSelect">{{
          $t('settingsServerSettingsZoneComponent.adminApprovalLabel')
        }}</label>
        <select
          class="form-select"
          name="serverSettingsAdminApprovalSelect"
          v-model="adminApproval"
          required
        >
          <option :value="false">
            {{ $t('generalItems.false') }}
          </option>
          <option :value="true">
            {{ $t('generalItems.true') }}
          </option>
        </select>
        <!-- requires email confirmation -->
        <label class="form-label" for="serverSettingsEmailConfirmationSelect">{{
          $t('settingsServerSettingsZoneComponent.emailConfirmationLabel')
        }}</label>
        <select
          class="form-select"
          name="serverSettingsEmailConfirmationSelect"
          v-model="emailConfirmation"
          required
        >
          <option :value="false">
            {{ $t('generalItems.false') }}
          </option>
          <option :value="true">
            {{ $t('generalItems.true') }}
          </option>
        </select>
      </div>
      <hr />

      <!-- SSO (Single Sign-On) -->
      <h4 class="mt-4">{{ $t('settingsServerSettingsZoneComponent.ssoTitle') }}</h4>
      <LoadingComponent v-if="isLoading" />
      <div v-else>
        <label class="form-label" for="serverSettingsSSOEnabledSelect">{{
          $t('settingsServerSettingsZoneComponent.enabledLabel')
        }}</label>
        <select
          class="form-select"
          name="serverSettingsSSOEnabledSelect"
          v-model="ssoEnabled"
          required
        >
          <option :value="false">
            {{ $t('generalItems.false') }}
          </option>
          <option :value="true">
            {{ $t('generalItems.true') }}
          </option>
        </select>
        <div class="alert alert-info mt-2" role="alert">
          <font-awesome-icon :icon="['fas', 'info-circle']" />
          <span class="ms-2">{{
            $t('settingsServerSettingsZoneComponent.ssoEnabledInfoAlert')
          }}</span>
        </div>
        <!-- Local login enabled -->
        <label class="form-label" for="serverSettingsLocalLoginEnabledSelect">{{
          $t('settingsServerSettingsZoneComponent.localLoginEnabledLabel')
        }}</label>
        <select
          class="form-select"
          name="serverSettingsLocalLoginEnabledSelect"
          v-model="localLoginEnabled"
          required
        >
          <option :value="false">
            {{ $t('generalItems.false') }}
          </option>
          <option :value="true">
            {{ $t('generalItems.true') }}
          </option>
        </select>
        <div class="alert alert-warning mt-2" role="alert">
          <font-awesome-icon :icon="['fas', 'triangle-exclamation']" />
          <span class="ms-2">{{
            $t('settingsServerSettingsZoneComponent.localLoginEnabledWarningAlert')
          }}</span>
        </div>
        <!-- SSO auto-redirect -->
        <label class="form-label" for="serverSettingsSSOAutoRedirectSelect">{{
          $t('settingsServerSettingsZoneComponent.ssoAutoRedirectLabel')
        }}</label>
        <select
          class="form-select"
          name="serverSettingsSSOAutoRedirectSelect"
          v-model="ssoAutoRedirect"
          required
        >
          <option :value="false">
            {{ $t('generalItems.false') }}
          </option>
          <option :value="true">
            {{ $t('generalItems.true') }}
          </option>
        </select>
        <div class="alert alert-info mt-2" role="alert">
          <font-awesome-icon :icon="['fas', 'info-circle']" />
          <span class="ms-2">{{
            $t('settingsServerSettingsZoneComponent.ssoAutoRedirectInfoAlert')
          }}</span>
        </div>
      </div>
      <hr />

      <!-- Public shareable links -->
      <h4 class="mt-4">
        {{ $t('settingsServerSettingsZoneComponent.publicShareableLinksLabel') }}
      </h4>
      <LoadingComponent v-if="isLoading" />
      <div v-else>
        <label class="form-label" for="serverSettingsPublicShareableLinksEnabledSelect">{{
          $t('settingsServerSettingsZoneComponent.enabledLabel')
        }}</label>
        <select
          class="form-select"
          name="serverSettingsPublicShareableLinksEnabledSelect"
          v-model="publicShareableLinks"
          required
        >
          <option :value="false">
            {{ $t('generalItems.false') }}
          </option>
          <option :value="true">
            {{ $t('generalItems.true') }}
          </option>
        </select>
        <div class="alert alert-warning mt-2" role="alert">
          <font-awesome-icon :icon="['fas', 'triangle-exclamation']" />
          <span class="ms-2">{{
            $t(
              'settingsServerSettingsZoneComponent.serverSettingsPublicShareableLinksEnabledWarningAlert'
            )
          }}</span>
        </div>
        <!-- Public shareable user info -->
        <label class="form-label" for="serverSettingsPublicShareableLinksShowUserInfo">{{
          $t('settingsServerSettingsZoneComponent.publicShareableLinksShowUserInfoLabel')
        }}</label>
        <select
          class="form-select"
          name="serverSettingsPublicShareableLinksShowUserInfo"
          v-model="publicShareableLinksUserInfo"
          required
        >
          <option :value="false">
            {{ $t('generalItems.false') }}
          </option>
          <option :value="true">
            {{ $t('generalItems.true') }}
          </option>
        </select>
        <div class="alert alert-warning mt-2" role="alert">
          <font-awesome-icon :icon="['fas', 'triangle-exclamation']" />
          <span class="ms-2">{{
            $t(
              'settingsServerSettingsZoneComponent.serverSettingsPublicShareableLinksShowUserWarningAlert'
            )
          }}</span>
        </div>
      </div>
      <hr />

      <!-- Maps -->
      <h4 class="mt-4">{{ $t('settingsServerSettingsZoneComponent.mapsTitle') }}</h4>
      <LoadingComponent v-if="isLoading" />
      <div v-else>
        <!-- Tile server template selector -->
        <label class="form-label" for="serverSettingsTileTemplate">{{
          $t('settingsServerSettingsZoneComponent.tileTemplateLabel')
        }}</label>
        <select
          class="form-select"
          name="serverSettingsTileTemplate"
          v-model="selectedTileTemplate"
          required
        >
          <option
            v-for="template in tileMapsTemplates"
            :key="template.template_id"
            :value="template.template_id"
          >
            {{ template.name }}
          </option>
          <option value="custom">
            {{ $t('settingsServerSettingsZoneComponent.tileTemplateCustom') }}
          </option>
        </select>
        <!-- API key warnings -->
        <div
          v-if="
            selectedTileTemplate !== 'custom' && getSelectedTemplateData()?.requires_api_key_backend
          "
          class="alert alert-warning mt-2"
          role="alert"
        >
          <font-awesome-icon :icon="['fas', 'triangle-exclamation']" />
          <span class="ms-2">{{
            $t('settingsServerSettingsZoneComponent.tileTemplateApiKeyWarning')
          }}</span>
        </div>
        <div
          v-if="
            selectedTileTemplate !== 'custom' &&
            getSelectedTemplateData()?.requires_api_key_frontend
          "
          class="alert alert-info mt-2"
          role="alert"
        >
          <font-awesome-icon :icon="['fas', 'info-circle']" />
          <span class="ms-2">{{
            $t('settingsServerSettingsZoneComponent.tileTemplateFrontendApiKeyWarning')
          }}</span>
        </div>
        <!-- Tile server URL -->
        <label class="form-label mt-2" for="serverSettingsTileserverUrl">{{
          $t('settingsServerSettingsZoneComponent.tileserverUrlLabel')
        }}</label>
        <input
          type="text"
          class="form-control"
          name="serverSettingsTileserverUrl"
          v-model="tileserverUrl"
          :disabled="selectedTileTemplate !== 'custom'"
          required
          @blur="updateServerSettings"
        />
        <!-- Tile server Attribution -->
        <label class="form-label mt-1" for="serverSettingsTileserverAttribution">{{
          $t('settingsServerSettingsZoneComponent.tileserverAttributionLabel')
        }}</label>
        <input
          type="text"
          class="form-control"
          name="serverSettingsTileserverAttribution"
          v-model="tileserverAttribution"
          :disabled="selectedTileTemplate !== 'custom'"
          required
          @blur="updateServerSettings"
        />
        <!-- Tile server Attribution -->
        <label class="form-label mt-1" for="serverSettingsTileserverApiKey">{{
          $t('settingsServerSettingsZoneComponent.tileserverApiKeyLabel')
        }}</label>
        <input
          type="text"
          class="form-control"
          name="serverSettingsTileserverApiKey"
          :placeholder="$t('settingsServerSettingsZoneComponent.tileserverApiKeyLabel')"
          v-model="tileserverApiKey"
          required
          @blur="updateServerSettings"
        />
        <!-- API key warnings -->
        <div class="alert alert-warning mt-2" role="alert">
          <font-awesome-icon :icon="['fas', 'triangle-exclamation']" />
          <span class="ms-2">{{
            $t('settingsServerSettingsZoneComponent.tileApiKeyWarning')
          }}</span>
        </div>
        <!-- Map Background Color -->
        <label class="form-label mt-1" for="serverSettingsMapBackgroundColor">{{
          $t('settingsServerSettingsZoneComponent.mapBackgroundColorLabel')
        }}</label>
        <div class="d-flex align-items-center gap-3">
          <input
            type="color"
            class="form-control form-control-color"
            name="serverSettingsMapBackgroundColor"
            v-model="mapBackgroundColor"
            :disabled="selectedTileTemplate !== 'custom'"
            required
          />
          <span>{{ mapBackgroundColor }}</span>
        </div>
      </div>
      <hr />
      <!-- Login photo set -->
      <h4 class="mt-4">{{ $t('settingsServerSettingsZoneComponent.photosLabel') }}</h4>
      <LoadingComponent v-if="isLoading" />
      <div v-else>
        <div class="row">
          <div class="col">
            <label class="form-label" for="serverSettingsLoginPhotoLabel">{{
              $t('settingsServerSettingsZoneComponent.loginPhotoLabel')
            }}</label>
            <!-- add login photo button -->
            <a
              class="w-100 btn btn-primary shadow-sm"
              href="#"
              role="button"
              data-bs-toggle="modal"
              data-bs-target="#addLoginPhotoModal"
              v-if="!loginPhotoSet"
            >
              {{ $t('settingsServerSettingsZoneComponent.buttonAddPhoto') }}
            </a>

            <!-- Delete login photo section -->
            <a
              class="w-100 btn btn-danger"
              href="#"
              role="button"
              data-bs-toggle="modal"
              data-bs-target="#deleteLoginPhotoModal"
              v-else
              >{{ $t('settingsServerSettingsZoneComponent.buttonDeleteLoginPhoto') }}</a
            >

            <!-- Modal add login photo -->
            <ModalComponentUploadFile
              modalId="addLoginPhotoModal"
              :title="$t('settingsServerSettingsZoneComponent.loginPhotoLabel')"
              :fileFieldLabel="$t('settingsServerSettingsZoneComponent.logonPhotoAddLabel')"
              filesAccepted=".png"
              actionButtonType="success"
              :actionButtonText="$t('settingsServerSettingsZoneComponent.loginPhotoLabel')"
              @fileToEmitAction="submitUploadFileForm"
            />

            <!-- Modal delete login photo -->
            <ModalComponent
              modalId="deleteLoginPhotoModal"
              :title="t('settingsServerSettingsZoneComponent.buttonDeleteLoginPhoto')"
              :body="`${t('settingsServerSettingsZoneComponent.modalDeleteLoginPhotoBody')}`"
              actionButtonType="danger"
              :actionButtonText="t('settingsServerSettingsZoneComponent.buttonDeleteLoginPhoto')"
              @submitAction="submitDeleteLoginPhoto"
            />
          </div>
        </div>
      </div>
    </form>
  </div>
</template>

<script setup>
import { ref, watch, onMounted, nextTick } from 'vue'
import { useI18n } from 'vue-i18n'
import { useServerSettingsStore } from '@/stores/serverSettingsStore'
import { serverSettings } from '@/services/serverSettingsService'
import { push } from 'notivue'
import ModalComponent from '@/components/Modals/ModalComponent.vue'
import ModalComponentUploadFile from '@/components/Modals/ModalComponentUploadFile.vue'
import LoadingComponent from '@/components/GeneralComponents/LoadingComponent.vue'

const { t } = useI18n()
const isLoading = ref(true)
const serverSettingsStore = useServerSettingsStore()
const tileMapsTemplates = ref([])
const selectedTileTemplate = ref('custom')
const units = ref(serverSettingsStore.serverSettings.units)
const currency = ref(serverSettingsStore.serverSettings.currency)
const numRecordsPerPage = ref(serverSettingsStore.serverSettings.num_records_per_page)
const publicShareableLinks = ref(serverSettingsStore.serverSettings.public_shareable_links)
const publicShareableLinksUserInfo = ref(
  serverSettingsStore.serverSettings.public_shareable_links_user_info
)
const loginPhotoSet = ref(serverSettingsStore.serverSettings.login_photo_set)
const signUp = ref(serverSettingsStore.serverSettings.signup_enabled)
const adminApproval = ref(serverSettingsStore.serverSettings.signup_require_admin_approval)
const emailConfirmation = ref(serverSettingsStore.serverSettings.signup_require_email_verification)
const ssoEnabled = ref(serverSettingsStore.serverSettings.sso_enabled)
const localLoginEnabled = ref(serverSettingsStore.serverSettings.local_login_enabled)
const ssoAutoRedirect = ref(serverSettingsStore.serverSettings.sso_auto_redirect)
const tileserverUrl = ref(serverSettingsStore.serverSettings.tileserver_url)
const tileserverAttribution = ref(serverSettingsStore.serverSettings.tileserver_attribution)
const tileserverApiKey = ref(serverSettingsStore.serverSettings.tileserver_api_key)
const mapBackgroundColor = ref(serverSettingsStore.serverSettings.map_background_color)
const passwordType = ref(serverSettingsStore.serverSettings.password_type)
const passwordLengthRegularUsers = ref(
  serverSettingsStore.serverSettings.password_length_regular_users
)
const passwordLengthAdminsUsers = ref(
  serverSettingsStore.serverSettings.password_length_admin_users
)

function getSelectedTemplateData() {
  if (selectedTileTemplate.value === 'custom') return null
  return tileMapsTemplates.value.find((t) => t.template_id === selectedTileTemplate.value)
}

function detectTemplateFromUrl(url) {
  const template = tileMapsTemplates.value.find((t) => t.url_template === url)
  return template ? template.template_id : 'custom'
}

async function updateServerSettings() {
  const data = {
    id: 1,
    units: units.value,
    currency: currency.value,
    num_records_per_page: numRecordsPerPage.value,
    public_shareable_links: publicShareableLinks.value,
    public_shareable_links_user_info: publicShareableLinksUserInfo.value,
    login_photo_set: loginPhotoSet.value,
    signup_enabled: signUp.value,
    signup_require_admin_approval: adminApproval.value,
    signup_require_email_verification: emailConfirmation.value,
    sso_enabled: ssoEnabled.value,
    local_login_enabled: localLoginEnabled.value,
    sso_auto_redirect: ssoAutoRedirect.value,
    tileserver_url: tileserverUrl.value,
    tileserver_attribution: tileserverAttribution.value,
    tileserver_api_key: tileserverApiKey.value,
    map_background_color: mapBackgroundColor.value,
    password_type: passwordType.value,
    password_length_regular_users: passwordLengthRegularUsers.value,
    password_length_admin_users: passwordLengthAdminsUsers.value
  }
  try {
    // Update the server settings in the DB
    await serverSettings.editServerSettings(data)

    // Update the server settings in the store
    serverSettingsStore.setServerSettings(data)

    push.success(t('settingsServerSettingsZoneComponent.successUpdateServerSettings'))
  } catch (error) {
    push.error(t('settingsServerSettingsZoneComponent.errorUpdateServerSettings'))
  }
}

const submitUploadFileForm = async (file) => {
  // Set the loading message
  const notification = push.promise(t('settingsServerSettingsZoneComponent.processingPhotoUpload'))

  // If there is a file, create the form data and upload the file
  if (file) {
    try {
      // Upload the file
      await serverSettings.uploadLoginPhotoFile(file)
      // Set the login photo set to true
      loginPhotoSet.value = true

      // Update the server settings in the store
      serverSettingsStore.serverSettings.login_photo_set = true

      // Set the success message
      notification.resolve(t('settingsServerSettingsZoneComponent.successPhotoUpload'))
    } catch (error) {
      // Set the error message
      notification.reject(`${error}`)
    }
  }
}

const submitDeleteLoginPhoto = async () => {
  // Set the loading message
  const notification = push.promise(t('settingsServerSettingsZoneComponent.processingPhotoDelete'))

  try {
    // Delete the login photo
    await serverSettings.deleteLoginPhotoFile()
    // Set the login photo set to false
    loginPhotoSet.value = false

    // Update the server settings in the store
    serverSettingsStore.serverSettings.login_photo_set = false

    // Set the success message
    notification.resolve(t('settingsServerSettingsZoneComponent.successPhotoDelete'))
  } catch (error) {
    // Set the error message
    notification.reject(`${error}`)
  }
}

onMounted(async () => {
  try {
    // Fetch tile map templates first
    tileMapsTemplates.value = await serverSettings.getTileMapsTemplates()

    // Fetch server settings and update store
    const settings = await serverSettings.getServerSettings()
    serverSettingsStore.setServerSettings(settings)
    // Update local state
    units.value = serverSettingsStore.serverSettings.units
    currency.value = serverSettingsStore.serverSettings.currency
    numRecordsPerPage.value = serverSettingsStore.serverSettings.num_records_per_page
    publicShareableLinks.value = serverSettingsStore.serverSettings.public_shareable_links
    publicShareableLinksUserInfo.value =
      serverSettingsStore.serverSettings.public_shareable_links_user_info
    loginPhotoSet.value = serverSettingsStore.serverSettings.login_photo_set
    signUp.value = serverSettingsStore.serverSettings.signup_enabled
    adminApproval.value = serverSettingsStore.serverSettings.signup_require_admin_approval
    emailConfirmation.value = serverSettingsStore.serverSettings.signup_require_email_verification
    ssoEnabled.value = serverSettingsStore.serverSettings.sso_enabled
    localLoginEnabled.value = serverSettingsStore.serverSettings.local_login_enabled
    ssoAutoRedirect.value = serverSettingsStore.serverSettings.sso_auto_redirect
    tileserverUrl.value = serverSettingsStore.serverSettings.tileserver_url
    tileserverAttribution.value = serverSettingsStore.serverSettings.tileserver_attribution
    tileserverApiKey.value = serverSettingsStore.serverSettings.tileserver_api_key
    mapBackgroundColor.value = serverSettingsStore.serverSettings.map_background_color
    passwordType.value = serverSettingsStore.serverSettings.password_type
    passwordLengthRegularUsers.value =
      serverSettingsStore.serverSettings.password_length_regular_users
    passwordLengthAdminsUsers.value = serverSettingsStore.serverSettings.password_length_admin_users

    // Detect template based on current URL
    selectedTileTemplate.value = detectTemplateFromUrl(tileserverUrl.value)

    await nextTick()
    isLoading.value = false
  } catch (error) {
    push.error(`${t('settingsServerSettingsZoneComponent.errorFetchingServerSettings')} - ${error}`)
    isLoading.value = false
  }
})

watch(
  [
    units,
    currency,
    numRecordsPerPage,
    publicShareableLinks,
    publicShareableLinksUserInfo,
    signUp,
    adminApproval,
    emailConfirmation,
    ssoEnabled,
    localLoginEnabled,
    ssoAutoRedirect,
    tileserverUrl,
    tileserverAttribution,
    tileserverApiKey,
    mapBackgroundColor,
    passwordType,
    passwordLengthRegularUsers,
    passwordLengthAdminsUsers
  ],
  async () => {
    if (isLoading.value === false) {
      await updateServerSettings()
    }
  },
  { immediate: false }
)

watch(selectedTileTemplate, async (newTemplate) => {
  if (isLoading.value) return

  if (newTemplate !== 'custom') {
    const templateData = getSelectedTemplateData()
    if (templateData) {
      tileserverUrl.value = templateData.url_template
      tileserverAttribution.value = templateData.attribution
      tileserverApiKey.value = null
      mapBackgroundColor.value = templateData.map_background_color
      await updateServerSettings()
    }
  }
})
</script>
