<template>
  <div
    class="modal fade"
    :id="
      action === 'add'
        ? 'addGearComponentModal'
        : action === 'edit'
          ? editGearComponentModalId
          : null
    "
    tabindex="-1"
    :aria-labelledby="
      action === 'add'
        ? 'addGearComponentModal'
        : action === 'edit'
          ? editGearComponentModalId
          : null
    "
    ref="addEditGearComponentModal"
    aria-hidden="true"
  >
    <div class="modal-dialog">
      <div class="modal-content">
        <div class="modal-header">
          <h1 class="modal-title fs-5" id="addGearComponentModal" v-if="action === 'add'">
            {{ $t('gearComponentAddEditModalComponent.addEditGearComponentModalAddTitle') }}
          </h1>
          <h1 class="modal-title fs-5" :id="editGearComponentModalId" v-else>
            {{ $t('gearComponentAddEditModalComponent.addEditGearComponentModalEditTitle') }}
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
            <!-- gear component type -->
            <label for="gearComponentTypeAddEdit"
              ><b
                >*
                {{
                  $t('gearComponentAddEditModalComponent.addEditGearComponentModalAddEditTypeLabel')
                }}</b
              ></label
            >
            <select
              class="form-select"
              name="gearComponentTypeAddEdit"
              v-model="newEditGearComponentType"
              required
            >
              <option
                v-for="type in GEAR_BIKE_COMPONENT_TYPES"
                :key="type"
                :value="type"
                v-if="gear.gear_type === 1"
              >
                {{ getGearBikeComponentType(type, t) }}
              </option>
              <option
                v-for="type in GEAR_SHOES_COMPONENT_TYPES"
                :key="type"
                :value="type"
                v-if="gear.gear_type === 2"
              >
                {{ getGearShoesComponentType(type, t) }}
              </option>
              <option
                v-for="type in GEAR_RACQUET_COMPONENT_TYPES"
                :key="type"
                :value="type"
                v-if="gear.gear_type === 4"
              >
                {{ getGearRacquetComponentType(type, t) }}
              </option>
              <option
                v-for="type in GEAR_WINDSURF_COMPONENT_TYPES"
                :key="type"
                :value="type"
                v-if="gear.gear_type === 7"
              >
                {{ getGearWindsurfComponentType(type, t) }}
              </option>
            </select>
            <!-- brand fields -->
            <label for="gearComponentBrandAddEdit"
              ><b
                >*
                {{
                  $t(
                    'gearComponentAddEditModalComponent.addEditGearComponentModalAddEditBrandLabel'
                  )
                }}</b
              ></label
            >
            <input
              class="form-control"
              type="text"
              name="gearComponentBrandAddEdit"
              :placeholder="
                $t('gearComponentAddEditModalComponent.addEditGearComponentModalAddEditBrandLabel')
              "
              v-model="newEditGearComponentBrand"
              maxlength="250"
            />
            <!-- model fields -->
            <label for="gearComponentModelAddEdit"
              ><b
                >*
                {{
                  $t(
                    'gearComponentAddEditModalComponent.addEditGearComponentModalAddEditModelLabel'
                  )
                }}</b
              ></label
            >
            <input
              class="form-control"
              type="text"
              name="gearComponentModelAddEdit"
              :placeholder="
                $t('gearComponentAddEditModalComponent.addEditGearComponentModalAddEditModelLabel')
              "
              v-model="newEditGearComponentModel"
              maxlength="250"
            />
            <!-- purchase date fields -->
            <label for="gearComponentPurchaseDateAddEdit"
              ><b
                >*
                {{
                  $t(
                    'gearComponentAddEditModalComponent.addEditGearComponentModalAddEditPurchaseDateLabel'
                  )
                }}</b
              ></label
            >
            <input
              class="form-control"
              type="date"
              name="gearComponentPurchaseDateAddEdit"
              v-model="newEditGearComponentPurchaseDate"
              required
            />
            <!-- expected distance -->
            <div v-if="gear.gear_type !== 4">
              <label for="gearComponentExpectedDistanceAddEdit"
                ><b>{{
                  $t(
                    'gearComponentAddEditModalComponent.addEditGearComponentModalAddEditExpectedDistanceLabel'
                  )
                }}</b></label
              >
              <div class="input-group">
                <input
                  class="form-control"
                  type="number"
                  name="gearComponentExpectedDistanceAddEdit"
                  :placeholder="
                    $t(
                      'gearComponentAddEditModalComponent.addEditGearComponentModalAddEditExpectedDistanceLabel'
                    )
                  "
                  v-model="newEditGearComponentExpectedDistanceKms"
                  min="0"
                  max="100000"
                  step="1"
                />
                <span class="input-group-text" v-if="authStore.user.units === 'metric'">{{
                  $t('generalItems.unitsKm')
                }}</span>
                <span class="input-group-text" v-else>{{ $t('generalItems.unitsMiles') }}</span>
              </div>
            </div>
            <!-- expected time -->
            <div v-if="gear.gear_type === 4">
              <label for="gearComponentExpectedTimeAddEdit"
                ><b>{{
                  $t(
                    'gearComponentAddEditModalComponent.addEditGearComponentModalAddEditExpectedTimeLabel'
                  )
                }}</b></label
              >
              <div class="input-group">
                <input
                  class="form-control"
                  type="number"
                  name="gearComponentExpectedTimeAddEdit"
                  :placeholder="
                    $t(
                      'gearComponentAddEditModalComponent.addEditGearComponentModalAddEditExpectedTimeLabel'
                    )
                  "
                  v-model="newEditGearComponentExpectedTime"
                  min="0"
                  max="100000"
                  step="1"
                />
                <span class="input-group-text">h</span>
              </div>
            </div>
            <!-- purchase value -->
            <label for="gearComponentPurchaseValueAddEdit"
              ><b>{{
                $t(
                  'gearComponentAddEditModalComponent.addEditGearComponentModalAddEditPurchaseValueLabel'
                )
              }}</b></label
            >
            <div class="input-group">
              <input
                class="form-control"
                type="number"
                name="addEditGearComponentModalAddEditPurchaseValueLabel"
                :placeholder="
                  $t(
                    'gearComponentAddEditModalComponent.addEditGearComponentModalAddEditPurchaseValueLabel'
                  )
                "
                v-model="newEditGearComponentPurchaseValue"
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
            <!-- retired rate -->
            <div v-if="action === 'edit'">
              <label for="gearComponentRetiredDateAddEdit"
                ><b>{{
                  $t(
                    'gearComponentAddEditModalComponent.addEditGearComponentModalAddEditRetiredDateLabel'
                  )
                }}</b></label
              >
              <input
                class="form-control"
                type="date"
                name="gearComponentRetiredDateAddEdit"
                v-model="newEditGearComponentRetiredDate"
              />
            </div>
            <!-- is active -->
            <div v-if="action === 'edit'">
              <label for="gearComponentIsActiveAddEdit"
                ><b
                  >*
                  {{
                    $t(
                      'gearComponentAddEditModalComponent.addEditGearComponentModalAddEditIsActiveLabel'
                    )
                  }}</b
                ></label
              >
              <select
                class="form-select"
                name="gearComponentIsActiveAddEdit"
                :disabled="newEditGearComponentRetiredDate"
                v-model="newEditGearComponentActive"
                required
              >
                <option :value="true">{{ $t('generalItems.yes') }}</option>
                <option :value="false">{{ $t('generalItems.no') }}</option>
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
              name="addGearComponent"
              data-bs-dismiss="modal"
              v-if="action === 'add'"
            >
              {{ $t('gearComponentAddEditModalComponent.addEditGearComponentModalAddTitle') }}
            </button>
            <button
              type="submit"
              class="btn btn-success"
              name="editGearComponent"
              data-bs-dismiss="modal"
              v-else
            >
              {{ $t('gearComponentAddEditModalComponent.addEditGearComponentModalEditTitle') }}
            </button>
          </div>
        </form>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { push } from 'notivue'
import { useAuthStore } from '@/stores/authStore'
import {
  GEAR_BIKE_COMPONENT_TYPES,
  getGearBikeComponentType,
  GEAR_SHOES_COMPONENT_TYPES,
  getGearShoesComponentType,
  GEAR_RACQUET_COMPONENT_TYPES,
  getGearRacquetComponentType,
  GEAR_WINDSURF_COMPONENT_TYPES,
  getGearWindsurfComponentType
} from '@/utils/gearComponentsUtils'
import { kmToMiles, milesToKm } from '@/utils/unitsUtils'
import { gearsComponents } from '@/services/gearsComponentsService'

const props = defineProps({
  action: {
    type: String,
    required: true
  },
  gear: {
    type: Object,
    required: true
  },
  gearComponent: {
    type: Object,
    required: false
  }
})
const emit = defineEmits([
  'isLoadingNewGearComponent',
  'createdGearComponent',
  'editedGearComponent'
])

const authStore = useAuthStore()
const { t } = useI18n()
const newEditGearComponentType = ref('back_break_oil')
const editGearComponentModalId = ref('')
const newEditGearComponentUserId = ref(null)
const newEditGearComponentGearId = ref(null)
const newEditGearComponentBrand = ref(null)
const newEditGearComponentModel = ref(null)
const newEditGearComponentPurchaseDate = ref(new Date().toISOString().split('T')[0])
const newEditGearComponentExpectedDistanceKms = ref(null)
const newEditGearComponentExpectedDistanceMiles = ref(null)
const newEditGearComponentExpectedTime = ref(null)
const newEditGearComponentPurchaseValue = ref(null)
const newEditGearComponentRetiredDate = ref(null)
const newEditGearComponentActive = ref(true)

onMounted(() => {
  newEditGearComponentUserId.value = props.gear.user_id
  newEditGearComponentGearId.value = props.gear.id
  if (props.gearComponent) {
    if (props.action === 'edit') {
      editGearComponentModalId.value = `editGearComponentModal${props.gearComponent.id}`
    }
    newEditGearComponentType.value = props.gearComponent.type
    newEditGearComponentBrand.value = props.gearComponent.brand
    newEditGearComponentModel.value = props.gearComponent.model
    newEditGearComponentPurchaseDate.value = props.gearComponent.purchase_date
    if (props.gear.gear_type !== 4) {
      newEditGearComponentExpectedDistanceKms.value = props.gearComponent.expected_kms / 1000
      if (props.gearComponent.expected_kms && props.gearComponent.expected_kms !== 0) {
        newEditGearComponentExpectedDistanceMiles.value = kmToMiles(
          props.gearComponent.expected_kms / 1000
        )
      }
    } else {
      newEditGearComponentExpectedTime.value = props.gearComponent.expected_kms / 3600
    }
    newEditGearComponentPurchaseValue.value = props.gearComponent.purchase_value
    newEditGearComponentRetiredDate.value = props.gearComponent.retired_date
    newEditGearComponentActive.value = props.gearComponent.active
  } else {
    if (props.gear.gear_type === 1) {
      newEditGearComponentType.value = 'back_break_oil'
    } else if (props.gear.gear_type === 2) {
      newEditGearComponentType.value = 'cleats'
    } else if (props.gear.gear_type === 4) {
      newEditGearComponentType.value = 'basegrip'
    } else if (props.gear.gear_type === 7) {
      newEditGearComponentType.value = 'sail'
    }
  }
})

function updateIsActiveBasedOnRetiredDate() {
  if (newEditGearComponentRetiredDate.value && newEditGearComponentRetiredDate.value !== '') {
    newEditGearComponentActive.value = false
  } else {
    newEditGearComponentRetiredDate.value = null
    newEditGearComponentActive.value = true
  }
}

async function submitAddGearComponentForm() {
  emit('isLoadingNewGearComponent', true)
  try {
    let expected_kms = null
    if (props.gear.gear_type !== 4) {
      expected_kms = newEditGearComponentExpectedDistanceKms.value * 1000
    } else {
      expected_kms = newEditGearComponentExpectedTime.value * 3600
    }
    const data = {
      user_id: newEditGearComponentUserId.value,
      gear_id: newEditGearComponentGearId.value,
      type: newEditGearComponentType.value,
      brand: newEditGearComponentBrand.value,
      model: newEditGearComponentModel.value,
      purchase_date: newEditGearComponentPurchaseDate.value,
      expected_kms: expected_kms,
      purchase_value: newEditGearComponentPurchaseValue.value
    }
    // add the gear component in the database
    const createdGearComponent = await gearsComponents.createGearComponent(data)
    // set the form values to default
    if (props.gear.gear_type === 1) {
      newEditGearComponentType.value = 'back_break_oil'
    } else if (props.gear.gear_type === 2) {
      newEditGearComponentType.value = 'cleats'
    } else if (props.gear.gear_type === 4) {
      newEditGearComponentType.value = 'basegrip'
    } else if (props.gear.gear_type === 7) {
      newEditGearComponentType.value = 'sail'
    }
    newEditGearComponentBrand.value = null
    newEditGearComponentModel.value = null
    newEditGearComponentPurchaseDate.value = new Date().toISOString().split('T')[0]
    newEditGearComponentExpectedDistanceKms.value = null
    newEditGearComponentExpectedDistanceMiles.value = null
    newEditGearComponentExpectedTime.value = null
    newEditGearComponentPurchaseValue.value = null
    // set the loading variable to false
    emit('isLoadingNewGearComponent', false)
    // emit the created gear component
    emit('createdGearComponent', createdGearComponent)
    // show success message
    push.success(t('gearComponentAddEditModalComponent.successGearComponentAdded'))
  } catch (error) {
    // if there is an error, show toast with error message
    push.error(`${t('gearComponentAddEditModalComponent.errorGearComponentAdd')} - ${error}`)
  } finally {
    // set the loading variable to false
    emit('isLoadingNewGearComponent', false)
  }
}

async function submitEditGearComponentForm() {
  try {
    let expected_kms = null
    if (props.gear.gear_type !== 4) {
      expected_kms = newEditGearComponentExpectedDistanceKms.value * 1000
    } else {
      expected_kms = newEditGearComponentExpectedTime.value * 3600
    }
    const data = {
      id: props.gearComponent.id,
      user_id: newEditGearComponentUserId.value,
      gear_id: newEditGearComponentGearId.value,
      type: newEditGearComponentType.value,
      brand: newEditGearComponentBrand.value,
      model: newEditGearComponentModel.value,
      purchase_date: newEditGearComponentPurchaseDate.value,
      retired_date: newEditGearComponentRetiredDate.value
        ? newEditGearComponentRetiredDate.value
        : null,
      active: newEditGearComponentActive.value,
      expected_kms: expected_kms,
      purchase_value: newEditGearComponentPurchaseValue.value
    }
    // change the gear component in the database
    await gearsComponents.editGearComponent(data)
    // emit the edited gear component
    emit('editedGearComponent', data)
    // show success message
    push.success(t('gearComponentAddEditModalComponent.gearComponentListGearEditSuccessMessage'))
  } catch (error) {
    push.error(
      `${t('gearComponentAddEditModalComponent.gearComponentListGearEditErrorMessage')} - ${error}`
    )
  }
}

function handleSubmit() {
  // Validation: retired_date must be after purchase_date if set
  if (
    newEditGearComponentRetiredDate.value &&
    newEditGearComponentPurchaseDate.value &&
    new Date(newEditGearComponentRetiredDate.value) <
      new Date(newEditGearComponentPurchaseDate.value)
  ) {
    push.error(t('gearComponentAddEditModalComponent.retiredDateAfterPurchaseDateError'))
    return
  }

  if (authStore?.user?.units === 'metric') {
    newEditGearComponentExpectedDistanceMiles.value = kmToMiles(
      newEditGearComponentExpectedDistanceKms.value
    )
  } else {
    newEditGearComponentExpectedDistanceKms.value = milesToKm(
      newEditGearComponentExpectedDistanceMiles.value
    )
  }
  if (props.action === 'add') {
    submitAddGearComponentForm()
  } else {
    submitEditGearComponentForm()
  }
}

// Watch the page number variable.
watch(newEditGearComponentRetiredDate, updateIsActiveBasedOnRetiredDate, { immediate: false })
</script>
