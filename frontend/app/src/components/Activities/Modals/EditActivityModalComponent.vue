<template>
  <!-- Modal edit activity -->
  <div
    class="modal fade"
    id="editActivityModal"
    tabindex="-1"
    aria-labelledby="editActivityModalComponent"
    aria-hidden="true"
  >
    <div class="modal-dialog">
      <div class="modal-content">
        <div class="modal-header">
          <h1 class="modal-title fs-5" id="editActivityModal">
            {{ $t('editActivityModalComponent.modalEditActivityTitle') }}
          </h1>
          <button
            type="button"
            class="btn-close"
            data-bs-dismiss="modal"
            aria-label="Close"
          ></button>
        </div>
        <form @submit.prevent="submitEditActivityForm">
          <div class="modal-body">
            <!-- name fields -->
            <label for="activityNameEdit"
              ><b>* {{ $t('editActivityModalComponent.modalEditActivityNameLabel') }}</b></label
            >
            <input
              class="form-control"
              type="text"
              name="activityNameEdit"
              :placeholder="$t('editActivityModalComponent.modalEditActivityNamePlaceholder')"
              maxlength="45"
              v-model="editActivityName"
              required
            />
            <!-- description fields -->
            <MarkdownEditorComponent
              v-model="editActivityDescription"
              :label="$t('editActivityModalComponent.modalEditActivityDescriptionLabel')"
              :placeholder="
                $t('editActivityModalComponent.modalEditActivityDescriptionPlaceholder')
              "
              :maxlength="2500"
              :rows="4"
              input-id="activityDescriptionEdit"
            />
            <!-- private_notes fields -->
            <MarkdownEditorComponent
              v-model="editActivityPrivateNotes"
              :label="$t('editActivityModalComponent.modalEditActivityPrivateNotesLabel')"
              :placeholder="
                $t('editActivityModalComponent.modalEditActivityPrivateNotesPlaceholder')
              "
              :maxlength="2500"
              :rows="4"
              input-id="activityPrivateNotesEdit"
            />
            <!-- type fields -->
            <label for="activityTypeEdit"
              ><b>* {{ $t('editActivityModalComponent.modalEditActivityTypeLabel') }}</b></label
            >
            <select class="form-select" name="activityTypeEdit" v-model="editActivityType" required>
              <option value="1">
                {{ $t('editActivityModalComponent.modalEditActivityTypeOption1') }}
              </option>
              <option value="2">
                {{ $t('editActivityModalComponent.modalEditActivityTypeOption2') }}
              </option>
              <option value="34">
                {{ $t('editActivityModalComponent.modalEditActivityTypeOption34') }}
              </option>
              <option value="40">
                {{ $t('editActivityModalComponent.modalEditActivityTypeOption40') }}
              </option>
              <option value="3">
                {{ $t('editActivityModalComponent.modalEditActivityTypeOption3') }}
              </option>
              <hr />
              <option value="4">
                {{ $t('editActivityModalComponent.modalEditActivityTypeOption4') }}
              </option>
              <option value="5">
                {{ $t('editActivityModalComponent.modalEditActivityTypeOption5') }}
              </option>
              <option value="6">
                {{ $t('editActivityModalComponent.modalEditActivityTypeOption6') }}
              </option>
              <option value="27">
                {{ $t('editActivityModalComponent.modalEditActivityTypeOption27') }}
              </option>
              <option value="28">
                {{ $t('editActivityModalComponent.modalEditActivityTypeOption28') }}
              </option>
              <option value="29">
                {{ $t('editActivityModalComponent.modalEditActivityTypeOption29') }}
              </option>
              <option value="35">
                {{ $t('editActivityModalComponent.modalEditActivityTypeOption35') }}
              </option>
              <option value="36">
                {{ $t('editActivityModalComponent.modalEditActivityTypeOption36') }}
              </option>
              <option value="7">
                {{ $t('editActivityModalComponent.modalEditActivityTypeOption7') }}
              </option>
              <hr />
              <option value="8">
                {{ $t('editActivityModalComponent.modalEditActivityTypeOption8') }}
              </option>
              <option value="9">
                {{ $t('editActivityModalComponent.modalEditActivityTypeOption9') }}
              </option>
              <hr />
              <option value="18">
                {{ $t('editActivityModalComponent.modalEditActivityTypeOption18') }}
              </option>
              <hr />
              <option value="10">
                {{ $t('editActivityModalComponent.modalEditActivityTypeOption10') }}
              </option>
              <option value="19">
                {{ $t('editActivityModalComponent.modalEditActivityTypeOption19') }}
              </option>
              <option value="20">
                {{ $t('editActivityModalComponent.modalEditActivityTypeOption20') }}
              </option>
              <option value="41">
                {{ $t('editActivityModalComponent.modalEditActivityTypeOption41') }}
              </option>
              <option value="46">
                {{ $t('editActivityModalComponent.modalEditActivityTypeOption46') }}
              </option>
              <hr />
              <option value="11">
                {{ $t('editActivityModalComponent.modalEditActivityTypeOption11') }}
              </option>
              <option value="31">
                {{ $t('editActivityModalComponent.modalEditActivityTypeOption31') }}
              </option>
              <option value="12">
                {{ $t('editActivityModalComponent.modalEditActivityTypeOption12') }}
              </option>
              <hr />
              <option value="13">
                {{ $t('editActivityModalComponent.modalEditActivityTypeOption13') }}
              </option>
              <option value="42">
                {{ $t('editActivityModalComponent.modalEditActivityTypeOption42') }}
              </option>
              <hr />
              <option value="14">
                {{ $t('editActivityModalComponent.modalEditActivityTypeOption14') }}
              </option>
              <hr />
              <option value="15">
                {{ $t('editActivityModalComponent.modalEditActivityTypeOption15') }}
              </option>
              <option value="16">
                {{ $t('editActivityModalComponent.modalEditActivityTypeOption16') }}
              </option>
              <option value="17">
                {{ $t('editActivityModalComponent.modalEditActivityTypeOption17') }}
              </option>
              <option value="37">
                {{ $t('editActivityModalComponent.modalEditActivityTypeOption37') }}
              </option>
              <option value="44">
                {{ $t('editActivityModalComponent.modalEditActivityTypeOption44') }}
              </option>
              <hr />
              <option value="21">
                {{ $t('editActivityModalComponent.modalEditActivityTypeOption21') }}
              </option>
              <option value="22">
                {{ $t('editActivityModalComponent.modalEditActivityTypeOption22') }}
              </option>
              <option value="23">
                {{ $t('editActivityModalComponent.modalEditActivityTypeOption23') }}
              </option>
              <option value="24">
                {{ $t('editActivityModalComponent.modalEditActivityTypeOption24') }}
              </option>
              <option value="25">
                {{ $t('editActivityModalComponent.modalEditActivityTypeOption25') }}
              </option>
              <option value="26">
                {{ $t('editActivityModalComponent.modalEditActivityTypeOption26') }}
              </option>
              <option value="39">
                {{ $t('editActivityModalComponent.modalEditActivityTypeOption39') }}
              </option>
              <hr />
              <option value="30">
                {{ $t('editActivityModalComponent.modalEditActivityTypeOption30') }}
              </option>
              <option value="32">
                {{ $t('editActivityModalComponent.modalEditActivityTypeOption32') }}
              </option>
              <option value="33">
                {{ $t('editActivityModalComponent.modalEditActivityTypeOption33') }}
              </option>
              <option value="43">
                {{ $t('editActivityModalComponent.modalEditActivityTypeOption43') }}
              </option>
              <hr />
              <option value="38">
                {{ $t('editActivityModalComponent.modalEditActivityTypeOption38') }}
              </option>
              <hr />
              <option value="45">
                {{ $t('editActivityModalComponent.modalEditActivityTypeOption45') }}
              </option>
            </select>
            <!-- visibility fields -->
            <label for="activityVisibilityEdit"
              ><b
                >* {{ $t('editActivityModalComponent.modalEditActivityVisibilityLabel') }}</b
              ></label
            >
            <select
              class="form-select"
              name="activityVisibilityEdit"
              v-model="editActivityVisibility"
              required
            >
              <option value="0">
                {{ $t('editActivityModalComponent.modalEditActivityVisibilityOption0') }}
              </option>
              <option value="1">
                {{ $t('editActivityModalComponent.modalEditActivityVisibilityOption1') }}
              </option>
              <option value="2">
                {{ $t('editActivityModalComponent.modalEditActivityVisibilityOption2') }}
              </option>
            </select>
            <!-- is_hidden fields-->
            <label for="activityIsHiddenEdit"
              ><b>* {{ $t('editActivityModalComponent.modalEditActivityIsHiddenLabel') }}</b></label
            >
            <select
              class="form-select"
              name="activityIsHiddenEdit"
              v-model="editActivityIsHidden"
              required
            >
              <option :value="true">{{ $t('generalItems.yes') }}</option>
              <option :value="false">{{ $t('generalItems.no') }}</option>
            </select>
            <div class="d-flex justify-content-start align-items-center">
              <span>{{ $t('editActivityModalComponent.modalEditActivityHiddenItemsLabel') }}</span>
              <!-- button toggle hidden fields -->
              <a
                class="btn btn-link btn-lg link-body-emphasis"
                data-bs-toggle="collapse"
                :href="`#collapseEditActivityHideFields`"
                role="button"
                aria-expanded="false"
                :aria-controls="`collapseEditActivityHideFields`"
              >
                <font-awesome-icon :icon="['fas', 'caret-down']" v-if="!hiddenFields" />
                <font-awesome-icon :icon="['fas', 'caret-up']" v-else />
              </a>
            </div>
            <div class="collapse" id="collapseEditActivityHideFields">
              <!-- hide start time fields -->
              <label for="activityHideStartTimeEdit"
                ><b
                  >* {{ $t('editActivityModalComponent.modalEditActivityHideStartTimeLabel') }}</b
                ></label
              >
              <select
                class="form-select"
                name="activityHideStartTimeEdit"
                v-model="editActivityHideStartTime"
                required
              >
                <option :value="true">{{ $t('generalItems.yes') }}</option>
                <option :value="false">{{ $t('generalItems.no') }}</option>
              </select>
              <!-- hide location fields -->
              <label for="activityHideLocationEdit"
                ><b
                  >* {{ $t('editActivityModalComponent.modalEditActivityHideLocationLabel') }}</b
                ></label
              >
              <select
                class="form-select"
                name="activityHideLocationEdit"
                v-model="editActivityHideLocation"
                required
              >
                <option :value="true">{{ $t('generalItems.yes') }}</option>
                <option :value="false">{{ $t('generalItems.no') }}</option>
              </select>
              <!-- hide map fields -->
              <label for="activityHideMapEdit"
                ><b
                  >* {{ $t('editActivityModalComponent.modalEditActivityHideMapLabel') }}</b
                ></label
              >
              <select
                class="form-select"
                name="activityHideMapEdit"
                v-model="editActivityHideMap"
                required
              >
                <option :value="true">{{ $t('generalItems.yes') }}</option>
                <option :value="false">{{ $t('generalItems.no') }}</option>
              </select>
              <!-- hide HR fields -->
              <label for="activityHideHrEdit"
                ><b>* {{ $t('editActivityModalComponent.modalEditActivityHideHrLabel') }}</b></label
              >
              <select
                class="form-select"
                name="activityHideHrEdit"
                v-model="editActivityHideHr"
                required
              >
                <option :value="true">{{ $t('generalItems.yes') }}</option>
                <option :value="false">{{ $t('generalItems.no') }}</option>
              </select>
              <!-- hide power fields -->
              <label for="activityHidePowerEdit"
                ><b
                  >* {{ $t('editActivityModalComponent.modalEditActivityHidePowerLabel') }}</b
                ></label
              >
              <select
                class="form-select"
                name="activityHidePowerEdit"
                v-model="editActivityHidePower"
                required
              >
                <option :value="true">{{ $t('generalItems.yes') }}</option>
                <option :value="false">{{ $t('generalItems.no') }}</option>
              </select>
              <!-- hide cadence fields -->
              <label for="activityHideCadenceEdit"
                ><b
                  >* {{ $t('editActivityModalComponent.modalEditActivityHideCadenceLabel') }}</b
                ></label
              >
              <select
                class="form-select"
                name="activityHideCadenceEdit"
                v-model="editActivityHideCadence"
                required
              >
                <option :value="true">{{ $t('generalItems.yes') }}</option>
                <option :value="false">{{ $t('generalItems.no') }}</option>
              </select>
              <!-- hide elevation fields -->
              <div v-if="!activityTypeIsSwimming(activity)">
                <label for="activityHideElevationEdit"
                  ><b
                    >* {{ $t('editActivityModalComponent.modalEditActivityHideElevationLabel') }}</b
                  ></label
                >
                <select
                  class="form-select"
                  name="activityHideElevationEdit"
                  v-model="editActivityHideElevation"
                  required
                >
                  <option :value="true">{{ $t('generalItems.yes') }}</option>
                  <option :value="false">{{ $t('generalItems.no') }}</option>
                </select>
              </div>
              <!-- hide speed fields -->
              <div v-if="activityTypeIsCycling(activity)">
                <label for="activityHideSpeedEdit"
                  ><b
                    >* {{ $t('editActivityModalComponent.modalEditActivityHideSpeedLabel') }}</b
                  ></label
                >
                <select
                  class="form-select"
                  name="activityHideSpeedEdit"
                  v-model="editActivityHideSpeed"
                  required
                >
                  <option :value="true">{{ $t('generalItems.yes') }}</option>
                  <option :value="false">{{ $t('generalItems.no') }}</option>
                </select>
              </div>
              <!-- hide pace fields -->
              <div
                v-if="
                  activityTypeIsRunning(activity) ||
                  activityTypeIsWalking(activity) ||
                  activityTypeIsSwimming(activity)
                "
              >
                <label for="activityHidePaceEdit"
                  ><b
                    >* {{ $t('editActivityModalComponent.modalEditActivityHidePaceLabel') }}</b
                  ></label
                >
                <select
                  class="form-select"
                  name="activityHidePaceEdit"
                  v-model="editActivityHidePace"
                  required
                >
                  <option :value="true">{{ $t('generalItems.yes') }}</option>
                  <option :value="false">{{ $t('generalItems.no') }}</option>
                </select>
              </div>
              <!-- hide laps fields -->
              <label for="activityHideLapsEdit"
                ><b
                  >* {{ $t('editActivityModalComponent.modalEditActivityHideLapsLabel') }}</b
                ></label
              >
              <select
                class="form-select"
                name="activityHideLapsEdit"
                v-model="editActivityHideLaps"
                required
              >
                <option :value="true">{{ $t('generalItems.yes') }}</option>
                <option :value="false">{{ $t('generalItems.no') }}</option>
              </select>
              <!-- hide workout sets/steps fields -->
              <label for="activityHideWorkoutSetsStepsEdit"
                ><b
                  >*
                  {{
                    $t('editActivityModalComponent.modalEditActivityHideWorkoutSetsStepsLabel')
                  }}</b
                ></label
              >
              <select
                class="form-select"
                name="activityHideWorkoutSetsStepsEdit"
                v-model="editActivityHideWorkoutSetsSteps"
                required
              >
                <option :value="true">{{ $t('generalItems.yes') }}</option>
                <option :value="false">{{ $t('generalItems.no') }}</option>
              </select>
              <!-- hide gear fields -->
              <label for="activityHideGearEdit"
                ><b
                  >* {{ $t('editActivityModalComponent.modalEditActivityHideGearLabel') }}</b
                ></label
              >
              <select
                class="form-select"
                name="activityHideGearEdit"
                v-model="editActivityHideGear"
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
            <button type="submit" class="btn btn-success" data-bs-dismiss="modal">
              {{ $t('editActivityModalComponent.modalEditActivityTitle') }}
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
// Importing the components
import MarkdownEditorComponent from '@/components/GeneralComponents/MarkdownEditorComponent.vue'
// Importing the services
import { activities } from '@/services/activitiesService'
// Importing the utils
import {
  activityTypeIsRunning,
  activityTypeIsCycling,
  activityTypeIsWalking,
  activityTypeIsSwimming
} from '@/utils/activityUtils'

// Define props
const props = defineProps({
  activity: {
    type: Object,
    required: true
  }
})

// Define emits
const emit = defineEmits(['activityEditedFields'])

// Setup
const { t } = useI18n()
const editActivityDescription = ref(props.activity.description)
const editActivityPrivateNotes = ref(props.activity.private_notes)
const editActivityName = ref(props.activity.name)
const editActivityType = ref(props.activity.activity_type)
const editActivityVisibility = ref(props.activity.visibility)
const editActivityIsHidden = ref(props.activity.is_hidden)
const hiddenFields = ref(false)
// Hide fields
const editActivityHideStartTime = ref(props.activity.hide_start_time)
const editActivityHideLocation = ref(props.activity.hide_location)
const editActivityHideMap = ref(props.activity.hide_map)
const editActivityHideHr = ref(props.activity.hide_hr)
const editActivityHidePower = ref(props.activity.hide_power)
const editActivityHideCadence = ref(props.activity.hide_cadence)
const editActivityHideElevation = ref(props.activity.hide_elevation)
const editActivityHideSpeed = ref(props.activity.hide_speed)
const editActivityHidePace = ref(props.activity.hide_pace)
const editActivityHideLaps = ref(props.activity.hide_laps)
const editActivityHideWorkoutSetsSteps = ref(props.activity.hide_workout_sets_steps)
const editActivityHideGear = ref(props.activity.hide_gear)

async function submitEditActivityForm() {
  try {
    const data = {
      id: props.activity.id,
      description: editActivityDescription.value,
      private_notes: editActivityPrivateNotes.value,
      name: editActivityName.value,
      activity_type: editActivityType.value,
      visibility: editActivityVisibility.value,
      is_hidden: editActivityIsHidden.value,
      hide_start_time: editActivityHideStartTime.value,
      hide_location: editActivityHideLocation.value,
      hide_map: editActivityHideMap.value,
      hide_hr: editActivityHideHr.value,
      hide_power: editActivityHidePower.value,
      hide_cadence: editActivityHideCadence.value,
      hide_elevation: editActivityHideElevation.value,
      hide_speed: editActivityHideSpeed.value,
      hide_pace: editActivityHidePace.value,
      hide_laps: editActivityHideLaps.value,
      hide_workout_sets_steps: editActivityHideWorkoutSetsSteps.value,
      hide_gear: editActivityHideGear.value
    }

    // Call the service to edit the activity
    await activities.editActivity(data)

    // show success toast
    push.success(t('editActivityModalComponent.successActivityEdit'))

    // Emit the activityEditedFields event to the parent component
    emit('activityEditedFields', data)
  } catch (error) {
    // If there is an error, set the error message and show the error alert.
    push.error(`${t('editActivityModalComponent.errorActivityEdit')} - ${error}`)
  }
}

onMounted(async () => {
  // Attach Bootstrap collapse event listeners to sync icon state
  const collapseElement = document.getElementById(`collapseEditActivityHideFields`)
  if (collapseElement) {
    collapseElement.addEventListener('show.bs.collapse', () => {
      hiddenFields.value = true
    })
    collapseElement.addEventListener('hide.bs.collapse', () => {
      hiddenFields.value = false
    })
  }
})
</script>
