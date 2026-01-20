<template>
  <!-- Modal add/edit user -->
  <div
    class="modal fade"
    :id="
      action == 'add'
        ? 'addUserModal'
        : action == 'edit'
          ? editUserModalId
          : action == 'profile'
            ? 'editProfileModal'
            : ''
    "
    tabindex="-1"
    :aria-labelledby="
      action == 'add'
        ? 'addUserModal'
        : action == 'edit'
          ? editUserModalId
          : action == 'profile'
            ? 'editProfileModal'
            : ''
    "
    aria-hidden="true"
  >
    <div class="modal-dialog">
      <div class="modal-content">
        <div class="modal-header">
          <h1 class="modal-title fs-5" id="addUserModal" v-if="action == 'add'">
            {{ $t('usersAddEditUserModalComponent.addEditUserModalAddTitle') }}
          </h1>
          <h1 class="modal-title fs-5" :id="editUserModalId" v-else-if="action == 'edit'">
            {{ $t('usersAddEditUserModalComponent.addEditUserModalEditTitle') }}
          </h1>
          <h1 class="modal-title fs-5" id="editProfileModal" v-else>
            {{ $t('usersAddEditUserModalComponent.addEditUserModalEditProfileTitle') }}
          </h1>
          <button
            type="button"
            class="btn-close"
            data-bs-dismiss="modal"
            aria-label="Close"
          ></button>
        </div>
        <form @submit.prevent="handleSubmit">
          <div class="modal-body">
            <label for="userImgAddEdit"
              ><b>{{
                $t('usersAddEditUserModalComponent.addEditUserModalUserPhotoLabel')
              }}</b></label
            >
            <div>
              <div class="row">
                <div class="col">
                  <input
                    class="form-control"
                    type="file"
                    accept="image/*"
                    name="userImgAddEdit"
                    :id="
                      action === 'edit' ? `userImgAddEdit-${user.id}` : `userImgAddEdit-${action}`
                    "
                    @change="handleFileChange"
                  />
                </div>
                <div class="col" v-if="newEditUserPhotoPath">
                  <a
                    class="w-100 btn btn-danger"
                    data-bs-dismiss="modal"
                    @click="submitDeleteUserPhoto"
                    >{{
                      $t('usersAddEditUserModalComponent.addEditUserModalDeleteUserPhotoButton')
                    }}</a
                  >
                </div>
              </div>
            </div>
            <!-- username fields -->
            <label for="userUsernameAddEdit"
              ><b
                >* {{ $t('usersAddEditUserModalComponent.addEditUserModalUsernameLabel') }}</b
              ></label
            >
            <input
              class="form-control"
              :class="{ 'is-invalid': !isUsernameExists }"
              type="text"
              name="userUsernameAddEdit"
              :placeholder="
                $t('usersAddEditUserModalComponent.addEditUserModalUsernamePlaceholder')
              "
              maxlength="250"
              v-model="newEditUserUsername"
              required
            />
            <div id="validationUsernameFeedback" class="invalid-feedback" v-if="!isUsernameExists">
              {{ $t('usersAddEditUserModalComponent.addEditUserModalErrorUsernameExists') }}
            </div>
            <!-- name fields -->
            <label for="userNameAddEdit"
              ><b>* {{ $t('usersAddEditUserModalComponent.addEditUserModalNameLabel') }}</b></label
            >
            <input
              class="form-control"
              type="text"
              name="userNameAddEdit"
              :placeholder="$t('usersAddEditUserModalComponent.addEditUserModalNamePlaceholder')"
              maxlength="250"
              v-model="newEditUserName"
              required
            />
            <!-- email fields -->
            <label for="userEmailAddEdit"
              ><b>* {{ $t('usersAddEditUserModalComponent.addEditUserModalEmailLabel') }}</b></label
            >
            <input
              class="form-control"
              :class="{ 'is-invalid': !isEmailValid || !isEmailExists }"
              type="text"
              name="userEmailAddEdit"
              :placeholder="$t('usersAddEditUserModalComponent.addEditUserModalEmailPlaceholder')"
              maxlength="45"
              v-model="newEditUserEmail"
              required
            />
            <div id="validationEmailFeedback" class="invalid-feedback" v-if="!isEmailValid">
              {{ $t('usersAddEditUserModalComponent.addEditUserModalErrorEmailInvalid') }}
            </div>
            <div id="validationEmailFeedback" class="invalid-feedback" v-else-if="!isEmailExists">
              {{ $t('usersAddEditUserModalComponent.addEditUserModalErrorEmailExists') }}
            </div>
            <!-- password fields -->
            <div v-if="action == 'add'">
              <label for="passUserAdd"
                ><b
                  >* {{ $t('usersAddEditUserModalComponent.addEditUserModalPasswordLabel') }}</b
                ></label
              >
              <div class="position-relative">
                <input
                  :type="showPassword ? 'text' : 'password'"
                  class="form-control"
                  :class="{ 'is-invalid': !isPasswordValid }"
                  id="validationPassword"
                  aria-describedby="validationPasswordFeedback"
                  name="passUserAdd"
                  :placeholder="
                    $t('usersAddEditUserModalComponent.addEditUserModalPasswordPlaceholder')
                  "
                  v-model="newUserPassword"
                  required
                />
                <button
                  type="button"
                  class="btn position-absolute top-50 end-0 translate-middle-y"
                  :class="{ 'me-4': !isPasswordValid }"
                  @click="togglePasswordVisibility"
                >
                  <font-awesome-icon :icon="showPassword ? ['fas', 'eye-slash'] : ['fas', 'eye']" />
                </button>
              </div>
              <div
                id="validationPasswordFeedback"
                class="invalid-feedback d-block"
                v-if="!isPasswordValid"
              >
                {{ $t('usersAddEditUserModalComponent.addEditUserModalErrorPasswordInvalid') }}
              </div>
            </div>
            <!-- city fields -->
            <label for="userCityAddEdit"
              ><b>{{ $t('usersAddEditUserModalComponent.addEditUserModalCityLabel') }}</b></label
            >
            <input
              class="form-control"
              type="text"
              name="userCityAddEdit"
              :placeholder="$t('usersAddEditUserModalComponent.addEditUserModalCityPlaceholder')"
              maxlength="45"
              v-model="newEditUserCity"
            />
            <!-- birth date fields -->
            <label for="userBirthDateAddEdit"
              ><b>{{
                $t('usersAddEditUserModalComponent.addEditUserModalBirthdayLabel')
              }}</b></label
            >
            <input
              class="form-control"
              type="date"
              name="userBirthDateAddEdit"
              v-model="newEditUserBirthDate"
            />
            <!-- gender fields -->
            <label for="userGenderAddEdit"
              ><b
                >* {{ $t('usersAddEditUserModalComponent.addEditUserModalGenderLabel') }}</b
              ></label
            >
            <select
              class="form-select"
              name="userGenderAddEdit"
              v-model="newEditUserGender"
              required
            >
              <option value="male">
                {{ $t('generalItems.genderMale') }}
              </option>
              <option value="female">
                {{ $t('generalItems.genderFemale') }}
              </option>
              <option value="unspecified">
                {{ $t('generalItems.genderUnspecified') }}
              </option>
            </select>
            <!-- units fields -->
            <label for="userUnitsAddEdit"
              ><b>* {{ $t('usersAddEditUserModalComponent.addEditUserModalUnitsLabel') }}</b></label
            >
            <select class="form-select" name="userUnitsAddEdit" v-model="newEditUserUnits" required>
              <option value="metric">
                {{ $t('usersAddEditUserModalComponent.addEditUserModalUnitsOption1') }}
              </option>
              <option value="imperial">
                {{ $t('usersAddEditUserModalComponent.addEditUserModalUnitsOption2') }}
              </option>
            </select>
            <!-- currency fields -->
            <label for="userCurrencyAddEdit"
              ><b
                >* {{ $t('usersAddEditUserModalComponent.addEditUserModalCurrencyLabel') }}</b
              ></label
            >
            <select
              class="form-select"
              name="userCurrencyAddEdit"
              v-model="newEditUserCurrency"
              required
            >
              <option value="euro">{{ $t('generalItems.currencyEuro') }}</option>
              <option value="dollar">{{ $t('generalItems.currencyDollar') }}</option>
              <option value="pound">{{ $t('generalItems.currencyPound') }}</option>
            </select>
            <!-- height fields -->
            <div v-if="authStore?.user?.units === 'metric'">
              <label for="userHeightAddEditCms"
                ><b
                  >{{ $t('usersAddEditUserModalComponent.addEditUserModalHeightLabel') }} ({{
                    $t('generalItems.unitsCm')
                  }})</b
                ></label
              >
              <div class="input-group">
                <input
                  class="form-control"
                  type="number"
                  name="userHeightAddEditCms"
                  :placeholder="
                    $t('usersAddEditUserModalComponent.addEditUserModalHeightPlaceholder')
                  "
                  v-model="newEditUserHeightCms"
                />
                <span class="input-group-text">{{ $t('generalItems.unitsCm') }}</span>
              </div>
            </div>
            <div v-else>
              <label for="userHeightAddEditFeetInches"
                ><b
                  >{{ $t('usersAddEditUserModalComponent.addEditUserModalHeightLabel') }} ({{
                    $t('generalItems.unitsFeetInches')
                  }})</b
                ></label
              >
              <div class="input-group">
                <input
                  class="form-control"
                  :class="{ 'is-invalid': !isFeetValid }"
                  type="number"
                  aria-describedby="validationFeetFeedback"
                  name="userHeightAddEditFeet"
                  :placeholder="
                    $t('usersAddEditUserModalComponent.addEditUserModalHeightPlaceholder')
                  "
                  v-model="newEditUserHeightFeet"
                  min="0"
                  max="10"
                  step="1"
                />
                <span class="input-group-text">{{ $t('generalItems.unitsFeet') }}</span>
                <input
                  class="form-control"
                  :class="{ 'is-invalid': !isInchesValid }"
                  type="number"
                  aria-describedby="validationInchesFeedback"
                  name="userHeightAddEditInches"
                  :placeholder="
                    $t('usersAddEditUserModalComponent.addEditUserModalHeightPlaceholder')
                  "
                  v-model="newEditUserHeightInches"
                  min="0"
                  max="11"
                  step="1"
                />
                <span class="input-group-text">{{ $t('generalItems.unitsInches') }}</span>
                <div id="validationFeetFeedback" class="invalid-feedback" v-if="!isFeetValid">
                  {{ $t('usersAddEditUserModalComponent.addEditUserModalFeetValidationLabel') }}
                </div>
                <div id="validationInchesFeedback" class="invalid-feedback" v-if="!isInchesValid">
                  {{ $t('usersAddEditUserModalComponent.addEditUserModalInchesValidationLabel') }}
                </div>
              </div>
            </div>
            <!-- max heart rate fields -->
            <label for="userMaxHeartRateAddEdit"
              ><b>{{
                $t('usersAddEditUserModalComponent.addEditUserModalMaxHeartRateLabel')
              }}</b></label
            >
            <div class="input-group">
              <input
                class="form-control"
                type="number"
                name="userMaxHeartRateAddEdit"
                :placeholder="
                  $t('usersAddEditUserModalComponent.addEditUserModalMaxHeartRatePlaceholder')
                "
                v-model="newEditUserMaxHeartRate"
                min="100"
                max="250"
                step="1"
              />
              <span class="input-group-text">{{ $t('generalItems.unitsBpm') }}</span>
            </div>
            <!-- preferred language fields -->
            <label for="userPreferredLanguageAddEdit"
              ><b
                >*
                {{
                  $t('usersAddEditUserModalComponent.addEditUserModalUserPreferredLanguageLabel')
                }}</b
              ></label
            >
            <select
              class="form-select"
              name="userPreferredLanguageAddEdit"
              v-model="newEditUserPreferredLanguage"
              required
            >
              <option value="ca">{{ $t('generalItems.languageOption2') }}</option>
              <option value="cn">{{ $t('generalItems.languageOption8') }}</option>
              <option value="tw">{{ $t('generalItems.languageOption9') }}</option>
              <option value="de">{{ $t('generalItems.languageOption4') }}</option>
              <option value="fr">{{ $t('generalItems.languageOption5') }}</option>
              <option value="gl">{{ $t('generalItems.languageOption10') }}</option>
              <option value="it">{{ $t('generalItems.languageOption11') }}</option>
              <option value="nl">{{ $t('generalItems.languageOption6') }}</option>
              <option value="pt">{{ $t('generalItems.languageOption3') }}</option>
              <option value="sl">{{ $t('generalItems.languageOption12') }}</option>
              <option value="sv">{{ $t('generalItems.languageOption13') }}</option>
              <option value="es">{{ $t('generalItems.languageOption7') }}</option>
              <option value="us">{{ $t('generalItems.languageOption1') }}</option>
            </select>
            <!-- first day of the week fields -->
            <label for="userFirstDayOfWeekAddEdit"
              ><b
                >*
                {{
                  $t('usersAddEditUserModalComponent.addEditUserModalUserFirstDayOfWeekLabel')
                }}</b
              ></label
            >
            <select
              class="form-select"
              name="userFirstDayOfWeekAddEdit"
              v-model="newEditUserFirstDayOfWeek"
              required
            >
              <option value="sunday">{{ $t('generalItems.firstDayOfWeekOption0') }}</option>
              <option value="monday">{{ $t('generalItems.firstDayOfWeekOption1') }}</option>
              <option value="tuesday">{{ $t('generalItems.firstDayOfWeekOption2') }}</option>
              <option value="wednesday">{{ $t('generalItems.firstDayOfWeekOption3') }}</option>
              <option value="thursday">{{ $t('generalItems.firstDayOfWeekOption4') }}</option>
              <option value="friday">{{ $t('generalItems.firstDayOfWeekOption5') }}</option>
              <option value="saturday">{{ $t('generalItems.firstDayOfWeekOption6') }}</option>
            </select>
            <!-- access type fields -->
            <div v-if="action != 'profile'">
              <label for="userTypeAddEdit"
                ><b
                  >* {{ $t('usersAddEditUserModalComponent.addEditUserModalUserTypeLabel') }}</b
                ></label
              >
              <select
                class="form-select"
                name="userTypeAddEdit"
                v-model="newEditUserAccessType"
                required
              >
                <option value="regular">
                  {{ $t('usersAddEditUserModalComponent.addEditUserModalUserTypeOption1') }}
                </option>
                <option value="admin">
                  {{ $t('usersAddEditUserModalComponent.addEditUserModalUserTypeOption2') }}
                </option>
              </select>
            </div>
            <!-- user active fields -->
            <div v-if="action != 'profile'">
              <label for="userActiveAddEdit"
                ><b
                  >* {{ $t('usersAddEditUserModalComponent.addEditUserModalIsActiveLabel') }}</b
                ></label
              >
              <select
                class="form-select"
                name="userActiveAddEdit"
                v-model="newEditUserActive"
                required
              >
                <option :value="true">
                  {{ $t('generalItems.yes') }}
                </option>
                <option :value="false">
                  {{ $t('generalItems.no') }}
                </option>
              </select>
            </div>

            <p>* {{ $t('generalItems.requiredField') }}</p>
          </div>
          <div class="modal-footer">
            <button type="button" class="btn btn-secondary" data-bs-dismiss="modal">
              {{ $t('generalItems.buttonClose') }}
            </button>
            <button
              type="submit"
              class="btn btn-success"
              name="userAdd"
              data-bs-dismiss="modal"
              v-if="action == 'add'"
              :disabled="!isPasswordValid || !isUsernameExists || !isEmailValid || !isEmailExists"
            >
              {{ $t('usersAddEditUserModalComponent.addEditUserModalAddTitle') }}
            </button>
            <button
              type="submit"
              class="btn btn-success"
              name="userEdit"
              data-bs-dismiss="modal"
              v-else-if="action == 'edit'"
              :disabled="
                !isFeetValid ||
                !isInchesValid ||
                !isUsernameExists ||
                !isEmailValid ||
                !isEmailExists
              "
            >
              {{ $t('usersAddEditUserModalComponent.addEditUserModalEditTitle') }}
            </button>
            <button
              type="submit"
              class="btn btn-success"
              name="userEdit"
              data-bs-dismiss="modal"
              v-else
              :disabled="
                !isFeetValid ||
                !isInchesValid ||
                !isUsernameExists ||
                !isEmailValid ||
                !isEmailExists
              "
            >
              {{ $t('usersAddEditUserModalComponent.addEditUserModalEditProfileTitle') }}
            </button>
          </div>
        </form>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { useAuthStore } from '@/stores/authStore'
import { useServerSettingsStore } from '@/stores/serverSettingsStore'
import { debounce } from 'lodash'
import { push } from 'notivue'
import { profile } from '@/services/profileService'
import { users } from '@/services/usersService'
import { cmToFeetInches, feetAndInchesToCm } from '@/utils/unitsUtils'
import { isValidPassword, buildPasswordRequirements } from '@/utils/validationUtils'

const props = defineProps({
  action: {
    type: String,
    required: true
  },
  user: {
    type: Object,
    required: false
  }
})
const emit = defineEmits(['userPhotoDeleted', 'isLoadingNewUser', 'createdUser', 'editedUser'])

const authStore = useAuthStore()
const serverSettingsStore = useServerSettingsStore()
const { t, locale } = useI18n()
const editUserModalId = ref('')
const newEditUserPhotoFile = ref(null)
const newEditUserUsername = ref('')
const newEditUserName = ref('')
const newEditUserEmail = ref('')
const newEditUserCity = ref(null)
const newEditUserBirthDate = ref(null)
const newEditUserGender = ref('male')
const newEditUserUnits = ref(serverSettingsStore.serverSettings.units)
const newEditUserCurrency = ref(serverSettingsStore.serverSettings.currency)
const newEditUserHeightCms = ref(null)
const newEditUserHeightFeet = ref(null)
const newEditUserHeightInches = ref(null)
const newEditUserMaxHeartRate = ref(null)
const newEditUserFirstDayOfWeek = ref('monday')
const isFeetValid = computed(
  () => newEditUserHeightFeet.value >= 0 && newEditUserHeightFeet.value <= 10
)
const isInchesValid = computed(
  () => newEditUserHeightInches.value >= 0 && newEditUserHeightInches.value <= 11
)
const newEditUserPreferredLanguage = ref('us')
const newEditUserAccessType = ref('regular')
const newEditUserActive = ref(true)
const newEditUserPhotoPath = ref(null)
const isUsernameExists = ref(true)
const isEmailExists = ref(true)
const isEmailValid = computed(() => {
  if (!newEditUserEmail.value) return true
  const emailRegex = /^[^\s@]{1,}@[^\s@]{2,}\.[^\s@]{2,}$/
  return emailRegex.test(newEditUserEmail.value)
})
const newUserPassword = ref('')
const isPasswordValid = computed(() => {
  if (!newUserPassword.value) return true

  const passwordType = serverSettingsStore.serverSettings.password_type
  const minLength =
    newEditUserAccessType.value === 'admin'
      ? serverSettingsStore.serverSettings.password_length_admin_users
      : serverSettingsStore.serverSettings.password_length_regular_users
  const requirements = buildPasswordRequirements(passwordType, minLength)

  return isValidPassword(newUserPassword.value, requirements)
})
const showPassword = ref(false)
const togglePasswordVisibility = () => {
  showPassword.value = !showPassword.value
}

if (props.user) {
  if (props.action === 'edit') {
    editUserModalId.value = `editUserModal${props.user.id}`
  }
  newEditUserUsername.value = props.user.username
  newEditUserName.value = props.user.name
  newEditUserEmail.value = props.user.email
  newEditUserCity.value = props.user.city
  newEditUserBirthDate.value = props.user.birthdate
  newEditUserGender.value = props.user.gender
  newEditUserUnits.value = props.user.units
  newEditUserCurrency.value = props.user.currency
  newEditUserHeightCms.value = props.user.height
  newEditUserMaxHeartRate.value = props.user.max_heart_rate
  newEditUserPreferredLanguage.value = props.user.preferred_language
  newEditUserFirstDayOfWeek.value = props.user.first_day_of_week
  newEditUserAccessType.value = props.user.access_type
  newEditUserActive.value = props.user.active
  newEditUserPhotoPath.value = props.user.photo_path
  if (props.user.height) {
    const { feet, inches } = cmToFeetInches(props.user.height)
    newEditUserHeightFeet.value = feet
    newEditUserHeightInches.value = inches
  }
}

const validateUsernameExists = debounce(async () => {
  let tryValidate = false
  if (props.action === 'edit' || props.action === 'profile') {
    if (newEditUserUsername.value !== props.user.username) {
      tryValidate = true
    }
  } else {
    if (props.action === 'add') {
      if (newEditUserUsername.value !== '') {
        tryValidate = true
      }
    }
  }
  if (tryValidate) {
    try {
      if (await users.getUserByUsername(newEditUserUsername.value)) {
        isUsernameExists.value = false
      } else {
        isUsernameExists.value = true
      }
    } catch (error) {
      push.error(
        `${t('usersAddEditUserModalComponent.addEditUserModalErrorFetchingUserByUsername')} - ${error}`
      )
    }
  } else {
    isUsernameExists.value = true
  }
}, 500)

const validateEmailExists = debounce(async () => {
  let tryValidate = false
  if (props.action === 'edit' || props.action === 'profile') {
    if (newEditUserEmail.value !== props.user.email) {
      tryValidate = true
    }
  } else {
    if (props.action === 'add') {
      if (newEditUserEmail.value !== '') {
        tryValidate = true
      }
    }
  }
  if (tryValidate) {
    if (isEmailValid.value) {
      try {
        if (await users.getUserByEmail(newEditUserEmail.value)) {
          isEmailExists.value = false
        } else {
          isEmailExists.value = true
        }
      } catch (error) {
        push.error(
          `${t('usersAddEditUserModalComponent.addEditUserModalErrorFetchingUserByEmail')} - ${error}`
        )
      }
    }
  } else {
    isEmailExists.value = true
  }
}, 500)

async function handleFileChange(event) {
  newEditUserPhotoFile.value = event.target.files?.[0] ?? null
}

async function submitDeleteUserPhoto() {
  try {
    await users.deleteUserPhoto(props.user.id)

    if (props.user.id === authStore.user.id || props.action === 'profile') {
      authStore.setPhotoPath(null)
    }

    emit('editedUser', { ...props.user, photo_path: null })

    push.success(t('usersAddEditUserModalComponent.addEditUserModalSuccessDeleteUserPhoto'))
  } catch (error) {
    push.error(
      `${t('usersAddEditUserModalComponent.addEditUserModalErrorDeleteUserPhoto')} - ${error}`
    )
  }
}

async function submitAddUserForm() {
  emit('isLoadingNewUser', true)
  try {
    if (isPasswordValid.value) {
      const data = {
        name: newEditUserName.value,
        username: newEditUserUsername.value.toLowerCase(),
        email: newEditUserEmail.value.toLowerCase(),
        city: newEditUserCity.value,
        birthdate: newEditUserBirthDate.value,
        preferred_language: newEditUserPreferredLanguage.value,
        gender: newEditUserGender.value,
        units: newEditUserUnits.value,
        currency: newEditUserCurrency.value,
        height: newEditUserHeightCms.value,
        max_heart_rate: newEditUserMaxHeartRate.value,
        access_type: newEditUserAccessType.value,
        photo_path: null,
        first_day_of_week: newEditUserFirstDayOfWeek.value,
        active: newEditUserActive.value,
        password: newUserPassword.value
      }
      const createdUser = await users.createUser(data)
      if (newEditUserPhotoFile.value) {
        try {
          createdUser.photo_path = await users.uploadImage(
            newEditUserPhotoFile.value,
            createdUser.id
          )
        } catch (error) {
          push.error(
            `${t('usersAddEditUserModalComponent.addEditUserModalErrorUploadingUserPhoto')} - ${error}`
          )
        }
      }
      emit('isLoadingNewUser', false)
      emit('createdUser', createdUser)
      push.success(t('usersAddEditUserModalComponent.addEditUserModalSuccessAddUser'))
    }
  } catch (error) {
    push.error(`${t('usersAddEditUserModalComponent.addEditUserModalErrorAddUser')} - ${error}`)
  } finally {
    emit('isLoadingNewUser', false)
  }
}

async function submitEditUserForm() {
  try {
    const data = {
      id: props.user.id,
      username: newEditUserUsername.value.toLowerCase(),
      name: newEditUserName.value,
      email: newEditUserEmail.value.toLowerCase(),
      city: newEditUserCity.value,
      birthdate: newEditUserBirthDate.value,
      gender: newEditUserGender.value,
      units: newEditUserUnits.value,
      currency: newEditUserCurrency.value,
      height: newEditUserHeightCms.value,
      max_heart_rate: newEditUserMaxHeartRate.value,
      preferred_language: newEditUserPreferredLanguage.value,
      first_day_of_week: newEditUserFirstDayOfWeek.value,
      access_type: newEditUserAccessType.value,
      photo_path: newEditUserPhotoPath.value,
      active: newEditUserActive.value
    }
    if (props.action === 'profile') {
      await profile.editProfile(data)
    } else {
      const editedUser = await users.editUser(data.id, data)
      data.external_auth_count = editedUser.external_auth_count
    }
    if (newEditUserPhotoFile.value) {
      try {
        if (props.action === 'profile') {
          data.photo_path = await profile.uploadProfileImage(newEditUserPhotoFile.value)
        } else {
          data.photo_path = await users.uploadImage(newEditUserPhotoFile.value, data.id)
        }
      } catch (error) {
        push.error(
          `${t('usersAddEditUserModalComponent.addEditUserModalErrorUploadingUserPhoto')} - ${error}`
        )
      }
    }
    if (props.action === 'edit') {
      emit('editedUser', data)
    }
    if (data.id === authStore.user.id || props.action === 'profile') {
      authStore.setUser(data, authStore.session_id, locale)
    }
    push.success(t('usersAddEditUserModalComponent.addEditUserModalSuccessEditUser'))
  } catch (error) {
    push.error(`${t('usersAddEditUserModalComponent.addEditUserModalErrorEditUser')} - ${error}`)
  }
}

function handleSubmit() {
  if (authStore?.user?.units === 'metric') {
    if (
      (props.user && newEditUserHeightCms.value !== props.user.height) ||
      props.action === 'add'
    ) {
      const { feet, inches } = cmToFeetInches(newEditUserHeightCms.value)
      newEditUserHeightFeet.value = feet
      newEditUserHeightInches.value = inches
    }
  } else {
    if (props.action === 'add') {
      newEditUserHeightCms.value = feetAndInchesToCm(
        newEditUserHeightFeet.value,
        newEditUserHeightInches.value
      )
    } else {
      const { feet, inches } = cmToFeetInches(props.user.height)
      if (feet !== newEditUserHeightFeet.value || inches !== newEditUserHeightInches.value) {
        newEditUserHeightCms.value = feetAndInchesToCm(
          newEditUserHeightFeet.value,
          newEditUserHeightInches.value
        )
      }
    }
  }
  if (props.action === 'add') {
    submitAddUserForm()
  } else {
    submitEditUserForm()
  }
}

watch(newEditUserUsername, validateUsernameExists, { immediate: false })
watch(newEditUserEmail, validateEmailExists, { immediate: false })
</script>
