<template>
  <div class="col">
    <div class="bg-body-tertiary rounded p-3 shadow-sm">
      <!-- add weight button -->
      <div class="d-flex">
        <a
          class="w-100 btn btn-primary shadow-sm me-1"
          href="#"
          role="button"
          data-bs-toggle="modal"
          data-bs-target="#addWeightModal"
          >{{ $t('healthWeightZoneComponent.buttonAddWeight') }}</a
        >
        <a
          class="w-100 btn btn-primary shadow-sm ms-1"
          href="#"
          role="button"
          data-bs-toggle="modal"
          data-bs-target="#addWeightTargetModal"
          >{{ $t('healthWeightZoneComponent.buttonWeightTarget') }}</a
        >
      </div>

      <HealthWeightAddEditModalComponent
        :action="'add'"
        @isLoadingNewWeight="updateIsLoadingNewWeight"
        @createdWeight="updateWeightListAdded"
      />

      <ModalComponentNumberInput
        modalId="addWeightTargetModal"
        :title="t('healthWeightZoneComponent.buttonWeightTarget')"
        :numberFieldLabel="t('healthWeightZoneComponent.modalWeightTargetLabel')"
        actionButtonType="success"
        :actionButtonText="t('generalItems.buttonSubmit')"
        :numberDefaultValue="props.userHealthTargets?.weight || parseInt(70)"
        @numberToEmitAction="submitSetWeightTarget"
      />

      <LoadingComponent v-if="isLoading" />
      <div v-else>
        <!-- Checking if userHealthWeight is loaded and has length -->
        <div v-if="userHealthWeight && userHealthWeight.length" class="mt-3">
          <!-- show graph -->
          <HealthWeightLineChartComponent
            :userHealthTargets="userHealthTargets"
            :userHealthWeight="userHealthWeight"
            :isLoading="isLoading"
          />

          <br />
          <p>
            {{ $t('healthWeightZoneComponent.labelNumberOfHealthWeightWeight1')
            }}{{ userHealthWeight.length
            }}{{ $t('healthWeightZoneComponent.labelNumberOfHealthWeightWeight2')
            }}{{ userHealthWeightPagination.length
            }}{{ $t('healthWeightZoneComponent.labelNumberOfHealthWeightWeight3') }}
          </p>

          <!-- Displaying loading new weight if applicable -->
          <ul class="mt-3 list-group list-group-flush" v-if="isLoadingNewWeight">
            <li class="list-group-item rounded">
              <LoadingComponent />
            </li>
          </ul>

          <!-- list zone -->
          <ul
            class="my-3 list-group list-group-flush"
            v-for="userHealthWeight in userHealthWeightPagination"
            :key="userHealthWeight.id"
            :userHealthWeight="userHealthWeight"
          >
            <HealthWeightListComponent
              :userHealthWeight="userHealthWeight"
              @deletedWeight="updateWeightListDeleted"
              @editedWeight="updateWeightListEdited"
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
        <NoItemsFoundComponent class="mt-3" :show-shadow="false" v-else />
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import { useI18n } from 'vue-i18n'
import HealthWeightAddEditModalComponent from './HealthWeightZone/HealthWeightAddEditModalComponent.vue'
import HealthWeightLineChartComponent from './HealthWeightZone/HealthWeightLineChartComponent.vue'
import HealthWeightListComponent from './HealthWeightZone/HealthWeightListComponent.vue'
import LoadingComponent from '../GeneralComponents/LoadingComponent.vue'
import NoItemsFoundComponent from '../GeneralComponents/NoItemsFoundComponents.vue'
import PaginationComponent from '../GeneralComponents/PaginationComponent.vue'
import ModalComponentNumberInput from '../Modals/ModalComponentNumberInput.vue'

const props = defineProps({
  userHealthWeight: {
    type: [Object, null],
    required: true
  },
  userHealthWeightPagination: {
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

const emit = defineEmits([
  'createdWeight',
  'deletedWeight',
  'editedWeight',
  'pageNumberChanged',
  'setWeightTarget'
])

const { t } = useI18n()
const isLoadingNewWeight = ref(false)

function updateIsLoadingNewWeight(isLoadingNewWeightNewValue) {
  isLoadingNewWeight.value = isLoadingNewWeightNewValue
}

function updateWeightListAdded(createdWeight) {
  emit('createdWeight', createdWeight)
}

function updateWeightListDeleted(deletedWeight) {
  emit('deletedWeight', deletedWeight)
}

function updateWeightListEdited(editedWeight) {
  emit('editedWeight', editedWeight)
}

function setPageNumber(page) {
  emit('pageNumberChanged', page)
}

function submitSetWeightTarget(weightTarget) {
  emit('setWeightTarget', weightTarget)
}
</script>
