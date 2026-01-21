<template>
  <!-- Modal add/edit weight -->
  <div
    class="modal fade"
    :id="action == 'add' ? 'addWeightModal' : action == 'edit' ? editWeightId : ''"
    tabindex="-1"
    :aria-labelledby="action == 'add' ? 'addWeightModal' : action == 'edit' ? editWeightId : ''"
    aria-hidden="true"
  >
    <div class="modal-dialog">
      <div class="modal-content">
        <div class="modal-header">
          <h1 class="modal-title fs-5" id="addWeightModal" v-if="action == 'add'">
            {{ $t('healthWeightAddEditModalComponent.addWeightModalTitle') }}
          </h1>
          <h1 class="modal-title fs-5" :id="editWeightId" v-else>
            {{ $t('healthWeightAddEditModalComponent.editWeightModalTitle') }}
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
            <!-- weight fields -->
            <label for="weightWeightAddEdit"
              ><b>* {{ $t('healthWeightAddEditModalComponent.addWeightWeightLabel') }}</b></label
            >
            <div class="input-group">
              <input
                class="form-control"
                type="number"
                step="0.01"
                name="weightWeightAddEdit"
                v-model="newEditWeightWeight"
                required
              />
              <span class="input-group-text" v-if="authStore?.user?.units === 'metric'">{{
                $t('generalItems.unitsKg')
              }}</span>
              <span class="input-group-text" v-else>{{ $t('generalItems.unitsLbs') }}</span>
            </div>
            <!-- date fields -->
            <label for="weightDateAddEdit"
              ><b>* {{ $t('healthWeightAddEditModalComponent.addWeightDateLabel') }}</b></label
            >
            <input
              class="form-control"
              type="date"
              name="weightDateAddEdit"
              v-model="newEditWeightDate"
              required
            />

            <div class="d-flex justify-content-start align-items-center">
              <span>{{ $t('healthWeightAddEditModalComponent.addWeightHiddenItemsLabel') }}</span>
              <!-- button toggle hidden fields -->
              <a
                class="btn btn-link btn-lg link-body-emphasis"
                data-bs-toggle="collapse"
                :href="`#collapseAddEditWeightDetailsFields`"
                role="button"
                aria-expanded="false"
                :aria-controls="`collapseAddEditWeightDetailsFields`"
              >
                <font-awesome-icon :icon="['fas', 'caret-down']" v-if="!detailFields" />
                <font-awesome-icon :icon="['fas', 'caret-up']" v-else />
              </a>
            </div>
            <div class="collapse" id="collapseAddEditWeightDetailsFields">
              <!-- bmi fields -->
              <label for="weightBMIAddEdit"
                ><b>* {{ $t('healthWeightAddEditModalComponent.addWeightBMILabel') }}</b></label
              >
              <input
                class="form-control"
                placeholder="20"
                type="number"
                step="0.01"
                name="weightBMIAddEdit"
                v-model="newEditWeightBMI"
              />
              <!-- body fat fields -->
              <label for="weightBodyFatAddEdit"
                ><b>* {{ $t('healthWeightAddEditModalComponent.addWeightBodyFatLabel') }}</b></label
              >
              <div class="input-group">
                <input
                  class="form-control"
                  placeholder="15"
                  type="number"
                  step="0.01"
                  name="weightBodyFatAddEdit"
                  v-model="newEditWeightBodyFat"
                />
                <span class="input-group-text">%</span>
              </div>
              <!-- body water fields -->
              <label for="weightBodyWaterAddEdit"
                ><b
                  >* {{ $t('healthWeightAddEditModalComponent.addWeightBodyWaterLabel') }}</b
                ></label
              >
              <div class="input-group">
                <input
                  class="form-control"
                  placeholder="60"
                  type="number"
                  step="0.01"
                  name="weightBodyWaterAddEdit"
                  v-model="newEditWeightBodyWater"
                />
                <span class="input-group-text">%</span>
              </div>
              <!-- bone mass fields -->
              <label for="weightBoneMassAddEdit"
                ><b
                  >* {{ $t('healthWeightAddEditModalComponent.addWeightBoneMassLabel') }}</b
                ></label
              >
              <div class="input-group">
                <input
                  class="form-control"
                  placeholder="5"
                  type="number"
                  step="0.01"
                  name="weightBoneMassAddEdit"
                  v-model="newEditWeightBoneMass"
                />
                <span class="input-group-text" v-if="authStore?.user?.units === 'metric'">{{
                  $t('generalItems.unitsKg')
                }}</span>
                <span class="input-group-text" v-else>{{ $t('generalItems.unitsLbs') }}</span>
              </div>
              <!-- muscle mass fields -->
              <label for="weightMuscleMassAddEdit"
                ><b
                  >* {{ $t('healthWeightAddEditModalComponent.addWeightMuscleMassLabel') }}</b
                ></label
              >
              <div class="input-group">
                <input
                  class="form-control"
                  placeholder="30"
                  type="number"
                  step="0.01"
                  name="weightMuscleMassAddEdit"
                  v-model="newEditWeightMuscleMass"
                />
                <span class="input-group-text" v-if="authStore?.user?.units === 'metric'">{{
                  $t('generalItems.unitsKg')
                }}</span>
                <span class="input-group-text" v-else>{{ $t('generalItems.unitsLbs') }}</span>
              </div>
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
              data-bs-dismiss="modal"
              v-if="action == 'add'"
            >
              {{ $t('healthWeightAddEditModalComponent.addWeightModalTitle') }}
            </button>
            <button type="submit" class="btn btn-success" data-bs-dismiss="modal" v-else>
              {{ $t('healthWeightAddEditModalComponent.editWeightModalTitle') }}
            </button>
          </div>
        </form>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
// Import Notivue push
import { push } from 'notivue'
// Importing the services
import { health_weight } from '@/services/health_weightService'
// Import the stores
import { useAuthStore } from '@/stores/authStore'
// Importing the utils
import { lbsToKg, kgToLbs } from '@/utils/unitsUtils'

const props = defineProps({
  action: {
    type: String,
    required: true
  },
  userHealthWeight: {
    type: Object,
    required: false
  }
})

const emit = defineEmits(['isLoadingNewWeight', 'createdWeight', 'editedWeight'])

const authStore = useAuthStore()
const { t } = useI18n()
const newEditWeightWeight = ref(50)
const newEditWeightDate = ref(new Date().toISOString().split('T')[0])
const newEditWeightBMI = ref(null)
const newEditWeightBodyFat = ref(null)
const newEditWeightBodyWater = ref(null)
const newEditWeightBoneMass = ref(null)
const newEditWeightMuscleMass = ref(null)
const editWeightId = ref('')
const detailFields = ref(false)

if (props.userHealthWeight) {
  newEditWeightWeight.value =
    authStore?.user?.units === 'metric'
      ? props.userHealthWeight.weight
      : kgToLbs(props.userHealthWeight.weight)
  newEditWeightDate.value = props.userHealthWeight.date
  newEditWeightBMI.value = props.userHealthWeight.bmi
  newEditWeightBodyFat.value = props.userHealthWeight.body_fat
  newEditWeightBodyWater.value = props.userHealthWeight.body_water
  newEditWeightBoneMass.value =
    authStore?.user?.units === 'metric'
      ? props.userHealthWeight.bone_mass
      : kgToLbs(props.userHealthWeight.bone_mass)
  newEditWeightMuscleMass.value =
    authStore?.user?.units === 'metric'
      ? props.userHealthWeight.muscle_mass
      : kgToLbs(props.userHealthWeight.muscle_mass)
  editWeightId.value = `editWeightId${props.userHealthWeight.id}`
}

async function submitAddWeight() {
  // Set the loading variable to true.
  emit('isLoadingNewWeight', true)
  try {
    let bone_mass = null
    let muscle_mass = null
    if (newEditWeightBoneMass.value !== null && newEditWeightBoneMass.value !== '') {
      bone_mass =
        authStore?.user?.units === 'metric'
          ? newEditWeightBoneMass.value
          : lbsToKg(newEditWeightBoneMass.value)
    }
    if (newEditWeightMuscleMass.value !== null && newEditWeightMuscleMass.value !== '') {
      muscle_mass =
        authStore?.user?.units === 'metric'
          ? newEditWeightMuscleMass.value
          : lbsToKg(newEditWeightMuscleMass.value)
    }
    // Create the weight data object.
    const data = {
      weight:
        authStore?.user?.units === 'metric'
          ? newEditWeightWeight.value
          : lbsToKg(newEditWeightWeight.value),
      date: newEditWeightDate.value,
      bmi:
        newEditWeightBMI.value !== null && newEditWeightBMI.value !== ''
          ? newEditWeightBMI.value
          : null,
      body_fat:
        newEditWeightBodyFat.value !== null && newEditWeightBodyFat.value !== ''
          ? newEditWeightBodyFat.value
          : null,
      body_water:
        newEditWeightBodyWater.value !== null && newEditWeightBodyWater.value !== ''
          ? newEditWeightBodyWater.value
          : null,
      bone_mass: bone_mass,
      muscle_mass: muscle_mass
    }

    const createdWeight = await health_weight.createHealthWeight(data)

    // Set the loading variable to false.
    emit('isLoadingNewWeight', false)

    // Get the created weight and emit it
    emit('createdWeight', createdWeight)

    push.success(t('healthWeightAddEditModalComponent.successAddWeight'))
  } catch (error) {
    // If there is an error, show toast with error message
    // Set the loading variable to false.
    emit('isLoadingNewWeight', false)
    push.error(`${t('healthWeightAddEditModalComponent.errorAddWeight')} - ${error.toString()}`)
  }
}

function submitEditWeight() {
  console.log(newEditWeightBodyFat.value)
  let bone_mass = null
  let muscle_mass = null
  if (newEditWeightBoneMass.value !== null && newEditWeightBoneMass.value !== '') {
    bone_mass =
      authStore?.user?.units === 'metric'
        ? newEditWeightBoneMass.value
        : lbsToKg(newEditWeightBoneMass.value)
  }
  if (newEditWeightMuscleMass.value !== null && newEditWeightMuscleMass.value !== '') {
    muscle_mass =
      authStore?.user?.units === 'metric'
        ? newEditWeightMuscleMass.value
        : lbsToKg(newEditWeightMuscleMass.value)
  }
  emit('editedWeight', {
    id: props.userHealthWeight.id,
    user_id: props.userHealthWeight.user_id,
    weight:
      authStore?.user?.units === 'metric'
        ? newEditWeightWeight.value
        : lbsToKg(newEditWeightWeight.value),
    date: newEditWeightDate.value,
    bmi:
      newEditWeightBMI.value !== null && newEditWeightBMI.value !== ''
        ? newEditWeightBMI.value
        : null,
    body_fat:
      newEditWeightBodyFat.value !== null && newEditWeightBodyFat.value !== ''
        ? newEditWeightBodyFat.value
        : null,
    body_water:
      newEditWeightBodyWater.value !== null && newEditWeightBodyWater.value !== ''
        ? newEditWeightBodyWater.value
        : null,
    bone_mass: bone_mass,
    muscle_mass: muscle_mass
  })
}

function handleSubmit() {
  if (props.action === 'add') {
    submitAddWeight()
  } else {
    submitEditWeight()
  }
}

onMounted(async () => {
  // Attach Bootstrap collapse event listeners to sync icon state
  const collapseElement = document.getElementById(`collapseAddEditWeightDetailsFields`)
  if (collapseElement) {
    collapseElement.addEventListener('show.bs.collapse', () => {
      detailFields.value = true
    })
    collapseElement.addEventListener('hide.bs.collapse', () => {
      detailFields.value = false
    })
  }
})
</script>
