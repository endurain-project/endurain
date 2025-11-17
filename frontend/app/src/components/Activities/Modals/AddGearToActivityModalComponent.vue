<template>
  <div
    class="modal fade"
    id="addGearToActivityModal"
    tabindex="-1"
    aria-labelledby="addGearToActivityModal"
    aria-hidden="true"
  >
    <div class="modal-dialog">
      <div class="modal-content">
        <div class="modal-header">
          <h1 class="modal-title fs-5" id="addGearToActivityModal">
            {{ $t('addGearToActivityModalComponent.modalLabelAddGear') }}
          </h1>
          <button
            type="button"
            class="btn-close"
            data-bs-dismiss="modal"
            aria-label="Close"
          ></button>
        </div>
        <form @submit.prevent="submitAddGearToActivityForm">
          <div class="modal-body">
            <!-- gear type fields -->
            <label for="gearIDAdd"
              ><b>* {{ $t('addGearToActivityModalComponent.modalLabelSelectGear') }}</b></label
            >
            <select class="form-select" name="gearIDAdd" v-model="gearId" required>
              <option v-for="gear in gearsByType" :key="gear.id" :value="gear.id">
                {{ gear.nickname }}
              </option>
            </select>
          </div>
          <div class="modal-footer">
            <button type="button" class="btn btn-secondary" data-bs-dismiss="modal">
              {{ $t('generalItems.buttonClose') }}
            </button>
            <button
              type="submit"
              class="btn btn-success"
              data-bs-dismiss="modal"
              name="addGearToActivity"
            >
              {{ $t('addGearToActivityModalComponent.modalButtonAddGear') }}
            </button>
          </div>
        </form>
      </div>
    </div>
  </div>
</template>

<script>
import { ref } from 'vue'
import { useI18n } from 'vue-i18n'
// Import Notivue push
import { push } from 'notivue'
// Importing the services
import { activities } from '@/services/activitiesService'

export default {
  props: {
    activity: {
      type: Object,
      required: true
    },
    gearsByType: {
      type: Array,
      required: true
    },
    gear: {
      type: [Number, null],
      required: true,
      default: null
    }
  },
  emits: ['gearId'],
  setup(props, { emit }) {
    const { t } = useI18n()
    const gearId = ref(props.gear || null)

    async function submitAddGearToActivityForm() {
      try {
        // Add the gear to the activity
        const auxActivity = props.activity
        auxActivity.gear_id = gearId.value
        await activities.editActivity(auxActivity)

        // Emit the gearId to the parent component
        emit('gearId', gearId.value)
      } catch (error) {
        push.error(`${t('addGearToActivityModalComponent.errorEditingGear')} - ${error}`)
      }
    }

    return {
      t,
      submitAddGearToActivityForm,
      gearId
    }
  }
}
</script>
