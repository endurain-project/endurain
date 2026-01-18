<template>
  <div
    class="modal fade"
    :id="action === 'add' ? 'addGearModal' : action === 'edit' ? editGearModalId : null"
    tabindex="-1"
    :aria-labelledby="
      action === 'add' ? 'addGearModal' : action === 'edit' ? editGearModalId : null
    "
    ref="addEditGearModal"
    aria-hidden="true"
  >
    <div class="modal-dialog">
      <div class="modal-content">
        <div class="modal-header">
          <h1 class="modal-title fs-5" id="addGearModal" v-if="action === 'add'">
            {{ $t('gearsAddEditGearModalComponent.addEditGearModalAddTitle') }}
          </h1>
          <h1 class="modal-title fs-5" :id="editGearModalId" v-else>
            {{ $t('gearsAddEditGearModalComponent.addEditGearModalEditTitle') }}
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
            <!-- brand fields -->
            <label for="gearBrandAddEdit"
              ><b>{{
                $t('gearsAddEditGearModalComponent.addEditGearModalAddBrandLabel')
              }}</b></label
            >
            <input
              class="form-control"
              type="text"
              name="gearBrandAddEdit"
              :placeholder="$t('gearsAddEditGearModalComponent.addEditGearModalAddBrandLabel')"
              v-model="newEditGearBrand"
              maxlength="250"
            />
            <!-- model fields -->
            <label for="gearModelAddEdit"
              ><b>{{
                $t('gearsAddEditGearModalComponent.addEditGearModalAddModelLabel')
              }}</b></label
            >
            <input
              class="form-control"
              type="text"
              name="gearModelAddEdit"
              :placeholder="$t('gearsAddEditGearModalComponent.addEditGearModalAddModelLabel')"
              v-model="newEditGearModel"
              maxlength="250"
            />
            <!-- nickname fields -->
            <label for="gearNicknameAddEdit"
              ><b
                >* {{ $t('gearsAddEditGearModalComponent.addEditGearModalAddNicknameLabel') }}</b
              ></label
            >
            <input
              class="form-control"
              :class="{ 'is-invalid': !isNicknameExists }"
              type="text"
              name="gearNicknameAddEdit"
              :placeholder="$t('gearsAddEditGearModalComponent.addEditGearModalAddNicknameLabel')"
              v-model="newEditGearNickname"
              maxlength="250"
              required
            />
            <div id="validationNicknameFeedback" class="invalid-feedback" v-if="!isNicknameExists">
              {{ $t('gearsAddEditGearModalComponent.errorNicknameAlreadyExistsFeedback') }}
            </div>
            <!-- gear type fields -->
            <label for="gearTypeAddEdit"
              ><b
                >* {{ $t('gearsAddEditGearModalComponent.addEditGearModalAddTypeLabel') }}</b
              ></label
            >
            <select class="form-select" name="gearTypeAddEdit" v-model="newEditGearType" required>
              <option value="1">
                {{ $t('gearsAddEditGearModalComponent.addEditGearModalAddTypeOption1') }}
              </option>
              <option value="2">
                {{ $t('gearsAddEditGearModalComponent.addEditGearModalAddTypeOption2') }}
              </option>
              <option value="3">
                {{ $t('gearsAddEditGearModalComponent.addEditGearModalAddTypeOption3') }}
              </option>
              <option value="4">
                {{ $t('gearsAddEditGearModalComponent.addEditGearModalAddTypeOption4') }}
              </option>
              <option value="5">
                {{ $t('gearsAddEditGearModalComponent.addEditGearModalAddTypeOption5') }}
              </option>
              <option value="6">
                {{ $t('gearsAddEditGearModalComponent.addEditGearModalAddTypeOption6') }}
              </option>
              <option value="7">
                {{ $t('gearsAddEditGearModalComponent.addEditGearModalAddTypeOption7') }}
              </option>
              <option value="8">
                {{ $t('gearsAddEditGearModalComponent.addEditGearModalAddTypeOption8') }}
              </option>
            </select>
            <!-- date fields -->
            <label for="gearDateAddEdit"
              ><b
                >* {{ $t('gearsAddEditGearModalComponent.addEditGearModalAddDateLabel') }}</b
              ></label
            >
            <input
              class="form-control"
              type="date"
              name="gearDateAddEdit"
              v-model="newEditGearCreatedDate"
              required
            />
            <!-- gear active fields -->
            <label for="gearActiveAddEdit"
              ><b
                >* {{ $t('gearsAddEditGearModalComponent.addEditGearModalAddIsActiveLabel') }}</b
              ></label
            >
            <select
              class="form-select"
              name="gearActiveAddEdit"
              v-model="newEditGearActive"
              required
            >
              <option value="true">
                {{ $t('gearsAddEditGearModalComponent.addEditGearModalAddIsActiveOption1') }}
              </option>
              <option value="false">
                {{ $t('gearsAddEditGearModalComponent.addEditGearModalAddIsActiveOption0') }}
              </option>
            </select>
            <!-- initial kilometers fields -->
            <div v-if="authStore?.user?.units === 'metric' && Number(newEditGearType) !== 4">
              <label for="gearInitialKmsAddEdit"
                ><b
                  >*
                  {{ $t('gearsAddEditGearModalComponent.addEditGearModalAddIsInitialKmsLabel') }}</b
                ></label
              >
              <input
                class="form-control"
                type="number"
                step="0.1"
                name="gearInitialKmsAddEdit"
                v-model="newEditGearInitialKms"
                required
              />
            </div>
            <!-- initial miles fields -->
            <div v-else-if="authStore?.user?.units === 'imperial' && Number(newEditGearType) !== 4">
              <label for="gearInitialMilesAddEdit"
                ><b
                  >*
                  {{
                    $t('gearsAddEditGearModalComponent.addEditGearModalAddIsInitialMilesLabel')
                  }}</b
                ></label
              >
              <input
                class="form-control"
                type="number"
                step="0.1"
                name="gearInitialMilesAddEdit"
                v-model="newEditGearInitialMiles"
                required
              />
            </div>
            <!-- purchase value -->
            <label for="gearPurchaseValueAddEdit"
              ><b>{{
                $t('gearsAddEditGearModalComponent.addEditGearModalAddEditPurchaseValueLabel')
              }}</b></label
            >
            <div class="input-group">
              <input
                class="form-control"
                type="number"
                name="gearPurchaseValueAddEdit"
                :placeholder="
                  $t('gearsAddEditGearModalComponent.addEditGearModalAddEditPurchaseValueLabel')
                "
                v-model="newEditGearPurchaseValue"
                min="0"
                max="100000"
                step="0.01"
                inputmode="decimal"
              />
              <span class="input-group-text" v-if="authStore.user.currency === 'euro'">{{
                $t('generalItems.currencyEuroSymbol')
              }}</span>
              <span class="input-group-text" v-else-if="authStore.user.currency === 'dollar'">{{
                $t('generalItems.currencyDollarSymbol')
              }}</span>
              <span class="input-group-text" v-else>{{
                $t('generalItems.currencyPoundSymbol')
              }}</span>
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
              name="addGear"
              data-bs-dismiss="modal"
              v-if="action === 'add'"
              :disabled="!isNicknameExists || !newEditGearCreatedDate || !newEditGearNickname"
            >
              {{ $t('gearsAddEditGearModalComponent.addEditGearModalAddTitle') }}
            </button>
            <button
              type="submit"
              class="btn btn-success"
              name="editGear"
              data-bs-dismiss="modal"
              v-else
              :disabled="!isNicknameExists || !newEditGearCreatedDate || !newEditGearNickname"
            >
              {{ $t('gearsAddEditGearModalComponent.addEditGearModalEditTitle') }}
            </button>
          </div>
        </form>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, watch, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { useAuthStore } from '@/stores/authStore'
import { debounce } from 'lodash'
import { push } from 'notivue'
import { gears } from '@/services/gearsService'
import { kmToMiles, milesToKm } from '@/utils/unitsUtils'

// defineProps and defineEmits for <script setup>
const props = defineProps({
  action: {
    type: String,
    required: true
  },
  gear: {
    type: Object,
    required: false
  }
})
const emit = defineEmits(['isLoadingNewGear', 'createdGear', 'editedGear'])

const authStore = useAuthStore()
const { t } = useI18n()
const editGearModalId = ref('')
const newEditGearBrand = ref('')
const newEditGearModel = ref('')
const newEditGearNickname = ref('')
const newEditGearType = ref(1)
const newEditGearCreatedDate = ref(new Date().toISOString().split('T')[0])
const newEditGearActive = ref(true)
const newEditGearInitialKms = ref(0)
const newEditGearInitialMiles = ref(0)
const newEditGearPurchaseValue = ref(0)
const isNicknameExists = ref(true)

const validateNicknameExists = debounce(async () => {
  let tryValidate = false
  if (props.action === 'edit') {
    if (newEditGearNickname.value !== props.gear.nickname) {
      tryValidate = true
    }
  } else {
    if (props.action === 'add') {
      if (newEditGearNickname.value !== '') {
        tryValidate = true
      }
    }
  }
  if (tryValidate) {
    try {
      if (await gears.getGearByNickname(newEditGearNickname.value)) {
        isNicknameExists.value = false
      } else {
        isNicknameExists.value = true
      }
    } catch (error) {
      push.error(
        `${t('gearsAddEditGearModalComponent.errorNotPossibleToGetGearByNickname')} - ${error}`
      )
    }
  } else {
    isNicknameExists.value = true
  }
}, 500)

onMounted(() => {
  if (props.gear) {
    if (props.action === 'edit') {
      editGearModalId.value = `editGearModal${props.gear.id}`
    }
    newEditGearBrand.value = props.gear.brand
    newEditGearModel.value = props.gear.model
    newEditGearNickname.value = props.gear.nickname
    newEditGearType.value = props.gear.gear_type
    newEditGearCreatedDate.value = props.gear.created_at
    newEditGearActive.value = props.gear.active
    newEditGearInitialKms.value = props.gear.initial_kms
    if (props.gear.initial_kms && props.gear.initial_kms !== 0) {
      newEditGearInitialMiles.value = kmToMiles(props.gear.initial_kms)
    }
    newEditGearPurchaseValue.value = props.gear.purchase_value
  }
})

async function submitAddGearForm() {
  emit('isLoadingNewGear', true)
  try {
    const data = {
      brand: newEditGearBrand.value,
      model: newEditGearModel.value,
      nickname: newEditGearNickname.value,
      gear_type: newEditGearType.value,
      created_at: newEditGearCreatedDate.value,
      active: newEditGearActive.value,
      initial_kms: newEditGearInitialKms.value,
      purchase_value: newEditGearPurchaseValue.value
    }
    // add the gear in the database
    const createdGear = await gears.createGear(data)
    // set the form values to default
    newEditGearBrand.value = ''
    newEditGearModel.value = ''
    newEditGearNickname.value = ''
    newEditGearType.value = 1
    newEditGearCreatedDate.value = new Date().toISOString().split('T')[0]
    newEditGearActive.value = true
    newEditGearInitialKms.value = 0
    newEditGearInitialMiles.value = 0
    newEditGearPurchaseValue.value = 0
    // set the loading variable to false
    emit('isLoadingNewGear', false)
    // emit the created gear
    emit('createdGear', createdGear)
    // show success message
    push.success(t('gearsAddEditGearModalComponent.successGearAdded'))
  } catch (error) {
    // if there is an error, show toast with error message
    push.error(`${t('gearsAddEditGearModalComponent.errorGearAdd')} - ${error}`)
  } finally {
    // set the loading variable to false
    emit('isLoadingNewGear', false)
  }
}

async function submitEditGearForm() {
  try {
    const data = {
      id: props.gear.id,
      brand: newEditGearBrand.value,
      model: newEditGearModel.value,
      nickname: newEditGearNickname.value,
      gear_type: newEditGearType.value,
      created_at: newEditGearCreatedDate.value,
      active: newEditGearActive.value,
      initial_kms: newEditGearInitialKms.value,
      purchase_value: newEditGearPurchaseValue.value
    }
    // change the gear in the database
    await gears.editGear(props.gear.id, data)
    // emit the edited gear
    emit('editedGear', data)
    // show success message
    push.success(t('gearsAddEditGearModalComponent.successGearEdited'))
  } catch (error) {
    push.error(`${t('gearsAddEditGearModalComponent.errorGearEdited')} - ${error}`)
  }
}

function handleSubmit() {
  if (authStore?.user?.units === 'metric') {
    if (
      (props.gear && newEditGearInitialKms.value !== props.gear.initial_kms) ||
      props.action === 'add'
    ) {
      newEditGearInitialMiles.value = kmToMiles(newEditGearInitialKms.initial_kms)
    }
  } else {
    if (props.action === 'add') {
      newEditGearInitialKms.value = milesToKm(newEditGearInitialMiles.value)
    } else {
      const miles = kmToMiles(props.gear.initial_kms)
      if (miles !== newEditGearInitialMiles.value) {
        newEditGearInitialKms.value = milesToKm(newEditGearInitialMiles.value)
      }
    }
  }
  if (props.action === 'add') {
    submitAddGearForm()
  } else {
    submitEditGearForm()
  }
}

watch(newEditGearNickname, validateNicknameExists, { immediate: false })
</script>
