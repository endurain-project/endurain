<template>
  <li class="list-group-item d-flex justify-content-between px-0 bg-body-tertiary">
    <div class="d-flex align-items-center">
      <img
        :src="getGearAvatar(gear.gear_type)"
        :alt="
          $t(
            `gearsListComponent.gearListTypeOption${
              gear.gear_type >= 1 && gear.gear_type <= 9 ? gear.gear_type : 1
            }`
          ) + ' avatar'
        "
        width="55"
        height="55"
        class="rounded-circle"
      />
      <div class="ms-3">
        <div class="fw-bold">
          <router-link
            :to="{ name: 'gear', params: { id: gear.id } }"
            class="link-body-emphasis link-underline-opacity-0 link-underline-opacity-100-hover"
          >
            {{ gear.nickname }}
          </router-link>
        </div>
        <b>{{ $t('gearsListComponent.gearListTypeLabel') }}: </b>
        <span v-if="gear.gear_type == 1">{{ $t('gearsListComponent.gearListTypeOption1') }}</span>
        <span v-else-if="gear.gear_type == 2">{{
          $t('gearsListComponent.gearListTypeOption2')
        }}</span>
        <span v-else-if="gear.gear_type == 3">{{
          $t('gearsListComponent.gearListTypeOption3')
        }}</span>
        <span v-else-if="gear.gear_type == 4">{{
          $t('gearsListComponent.gearListTypeOption4')
        }}</span>
        <span v-else-if="gear.gear_type == 5">{{
          $t('gearsListComponent.gearListTypeOption5')
        }}</span>
        <span v-else-if="gear.gear_type == 6">{{
          $t('gearsListComponent.gearListTypeOption6')
        }}</span>
        <span v-else-if="gear.gear_type == 7">{{
          $t('gearsListComponent.gearListTypeOption7')
        }}</span>
        <span v-else-if="gear.gear_type == 8">{{
          $t('gearsListComponent.gearListTypeOption8')
        }}</span>
        <span v-else-if="gear.gear_type == 9">{{
          $t('gearsListComponent.gearListTypeOption9')
        }}</span>
        <span v-else>{{ $t('gearsListComponent.gearListTypeOption1') }}</span>
        <br />
      </div>
    </div>
    <div>
      <span class="align-middle me-4 d-none d-sm-inline" v-if="gear.strava_gear_id">
        <font-awesome-icon :icon="['fab', 'fa-strava']" />
      </span>
      <span class="align-middle me-3 d-none d-sm-inline" v-if="gear.garminconnect_gear_id">
        <img :src="INTEGRATION_LOGOS.garminConnectApp" alt="Garmin Connect logo" height="22" />
      </span>
      <span
        class="badge bg-danger-subtle border border-danger-subtle text-danger-emphasis align-middle d-none d-sm-inline"
        v-if="gear.active == false"
        >{{ $t('gearsListComponent.gearListGearIsInactiveBadge') }}</span
      >

      <!-- edit gear button -->
      <a
        class="btn btn-link btn-lg link-body-emphasis d-none d-sm-inline"
        href="#"
        role="button"
        data-bs-toggle="modal"
        :data-bs-target="`#editGearModal${gear.id}`"
        ><font-awesome-icon :icon="['fas', 'fa-pen-to-square']"
      /></a>

      <GearsAddEditGearModalComponent :action="'edit'" :gear="gear" @editedGear="editGearList" />

      <!-- delete gear button -->
      <a
        class="btn btn-link btn-lg link-body-emphasis d-none d-sm-inline"
        href="#"
        role="button"
        data-bs-toggle="modal"
        :data-bs-target="`#deleteGearModal${gear.id}`"
        ><font-awesome-icon :icon="['fas', 'fa-trash-can']"
      /></a>

      <!-- delete gear modal -->
      <ModalComponent
        :modalId="`deleteGearModal${gear.id}`"
        :title="t('gearsListComponent.gearListModalDeleteGearTitle')"
        :body="`${t('gearsListComponent.gearListModalDeleteGearBody')}<b>${gear.nickname}</b>?`"
        :actionButtonType="`danger`"
        :actionButtonText="t('gearsListComponent.gearListModalDeleteGearTitle')"
        @submitAction="submitDeleteGear"
      />
    </div>
  </li>
</template>

<script setup>
import { useI18n } from 'vue-i18n'
import { gears } from '@/services/gearsService'
import { push } from 'notivue'
import ModalComponent from '@/components/Modals/ModalComponent.vue'
import GearsAddEditGearModalComponent from '@/components/Gears/GearsAddEditGearModalComponent.vue'
import { getGearAvatar } from '@/constants/gearAvatarConstants'
import { INTEGRATION_LOGOS } from '@/constants/integrationLogoConstants'

const props = defineProps({
  gear: {
    type: Object,
    required: true
  }
})
const emit = defineEmits(['gearDeleted', 'editedGear'])

const { t } = useI18n()

async function submitDeleteGear() {
  try {
    await gears.deleteGear(props.gear.id)
    emit('gearDeleted', props.gear.id)
    push.success(t('gearsListComponent.gearListGearDeleteSuccessMessage'))
  } catch (error) {
    push.error(`${t('gearsListComponent.gearListGearDeleteErrorMessage')} - ${error}`)
  }
}

function editGearList(editedGear) {
  emit('editedGear', editedGear)
}
</script>
