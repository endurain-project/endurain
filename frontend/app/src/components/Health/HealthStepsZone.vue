<template>
  <div class="col">
    <LoadingComponent v-if="isLoading" />
    <div v-else>
      <!-- add steps button -->
      <div class="d-flex">
        <a
          class="w-100 btn btn-primary shadow-sm me-1"
          href="#"
          role="button"
          data-bs-toggle="modal"
          data-bs-target="#addStepsModal"
          >{{ $t('healthStepsZoneComponent.buttonAddSteps') }}</a
        >
        <a
          class="w-100 btn btn-primary shadow-sm ms-1"
          href="#"
          role="button"
          data-bs-toggle="modal"
          data-bs-target="#addStepsTargetModal"
          >{{ $t('healthStepsZoneComponent.buttonStepsTarget') }}</a
        >
      </div>

      <HealthStepsAddEditModalComponent
        :action="'add'"
        @isLoadingNewSteps="updateIsLoadingNewSteps"
        @createdSteps="updateStepsListAdded"
      />

      <ModalComponentNumberInput 
        modalId="addStepsTargetModal" 
        :title="t('healthStepsZoneComponent.buttonStepsTarget')" 
        :numberFieldLabel="t('healthStepsZoneComponent.modalStepsTargetLabel')"
        actionButtonType="success"
        :actionButtonText="t('generalItems.buttonSubmit')"
        :numberDefaultValue="props.userHealthTargets?.steps || parseInt(10000)"
        @numberToEmitAction="submitSetStepsTarget"
      />

      <!-- Checking if userHealthSteps is loaded and has length -->
      <div
        v-if="userHealthSteps && userHealthSteps.length"
        class="mt-3 p-3 bg-body-tertiary rounded shadow-sm"
      >
        <!-- show graph -->
        <HealthStepsBarChartComponent :userHealthTargets="userHealthTargets":userHealthSteps="userHealthSteps" :isLoading="isLoading" />

        <br />
        <p>
          {{ $t('healthStepsZoneComponent.labelNumberOfHealthSteps1')
          }}{{ userHealthSteps.length
          }}{{ $t('healthStepsZoneComponent.labelNumberOfHealthSteps2')
          }}{{ userHealthStepsPagination.length
          }}{{ $t('healthStepsZoneComponent.labelNumberOfHealthSteps3') }}
        </p>

        <!-- Displaying loading new steps if applicable -->
        <ul class="mt-3 list-group list-group-flush" v-if="isLoadingNewSteps">
          <li class="list-group-item rounded">
            <LoadingComponent />
          </li>
        </ul>

        <!-- list zone -->
        <ul
          class="my-3 list-group list-group-flush"
          v-for="data in userHealthStepsPagination"
          :key="data.id"
          :data="data"
        >
          <HealthStepsListComponent
            :data="data"
            @deletedSteps="updateStepsListDeleted"
            @editedSteps="updateStepsListEdited"
          />
        </ul>

        <!-- pagination area -->
        <PaginationComponent
          :totalPages="totalPages"
          :pageNumber="pageNumber"
          @pageNumberChanged="setPageNumber"
        />
      </div>
      <!-- Displaying a message or component when there are no weight measurements -->
      <div v-else class="mt-3">
        <br />
        <NoItemsFoundComponent />
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import { useI18n } from 'vue-i18n'
import HealthStepsAddEditModalComponent from './HealthStepsZone/HealthStepsAddEditModalComponent.vue'
import HealthStepsBarChartComponent from './HealthStepsZone/HealthStepsBarChartComponent.vue'
import HealthStepsListComponent from './HealthStepsZone/HealthStepsListComponent.vue'
import LoadingComponent from '../GeneralComponents/LoadingComponent.vue'
import NoItemsFoundComponent from '../GeneralComponents/NoItemsFoundComponents.vue'
import PaginationComponent from '../GeneralComponents/PaginationComponent.vue'
import ModalComponentNumberInput from '../Modals/ModalComponentNumberInput.vue'

const props = defineProps({
  userHealthSteps: {
    type: [Object, null],
    required: true
  },
  userHealthStepsPagination: {
    type: [Object, null],
    required: true
  },
  userHealthTargets: {
    type: [Object, null],
    required: true
  },
  isLoading: {
    type: Boolean,
    required: true
  },
  totalPages: {
    type: Number,
    required: true
  },
  pageNumber: {
    type: Number,
    required: true
  }
})

const emit = defineEmits(['createdSteps', 'deletedSteps', 'editedSteps', 'pageNumberChanged', 'setStepsTarget'])

const { t } = useI18n()
const isLoadingNewSteps = ref(false)

function updateIsLoadingNewSteps(isLoadingNewStepsNewValue) {
  isLoadingNewSteps.value = isLoadingNewStepsNewValue
}

function updateStepsListAdded(createdSteps) {
  emit('createdSteps', createdSteps)
}

function updateStepsListDeleted(deletedSteps) {
  emit('deletedSteps', deletedSteps)
}

function updateStepsListEdited(editedSteps) {
  emit('editedSteps', editedSteps)
}

function setPageNumber(page) {
  emit('pageNumberChanged', page)
}

function submitSetStepsTarget(stepsTarget) {
  emit('setStepsTarget', stepsTarget)
}
</script>