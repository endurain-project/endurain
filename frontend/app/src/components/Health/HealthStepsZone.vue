<template>
  <div class="col">
    <LoadingComponent v-if="isLoading" />
    <div v-else>
      <!-- add weight button -->
      <a
        class="w-100 btn btn-primary shadow-sm"
        href="#"
        role="button"
        data-bs-toggle="modal"
        data-bs-target="#addStepsModal"
        >{{ $t('healthStepsZoneComponent.buttonAddSteps') }}</a
      >

      <HealthStepsAddEditModalComponent
        :action="'add'"
        @isLoadingNewSteps="updateIsLoadingNewSteps"
        @createdSteps="updateStepsListAdded"
      />

      <!-- Checking if dataWithSteps is loaded and has length -->
      <div
        v-if="dataWithSteps && dataWithSteps.length"
        class="mt-3 p-3 bg-body-tertiary rounded shadow-sm"
      >
        <!-- show graph -->
        <HealthStepsBarChartComponent :userHealthTargets="userHealthTargets":userHealthSteps="dataWithSteps" :isLoading="isLoading" />

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
          v-for="data in dataWithStepsPagination"
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
import { ref, watchEffect, onMounted } from 'vue'
import HealthStepsAddEditModalComponent from './HealthStepsZone/HealthStepsAddEditModalComponent.vue'
import HealthStepsBarChartComponent from './HealthStepsZone/HealthStepsBarChartComponent.vue'
import HealthStepsListComponent from './HealthStepsZone/HealthStepsListComponent.vue'
import LoadingComponent from '../GeneralComponents/LoadingComponent.vue'
import NoItemsFoundComponent from '../GeneralComponents/NoItemsFoundComponents.vue'
import PaginationComponent from '../GeneralComponents/PaginationComponent.vue'

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

const emit = defineEmits(['createdSteps', 'deletedSteps', 'editedSteps', 'pageNumberChanged'])

const dataWithSteps = ref([])
const dataWithStepsPagination = ref([])
const isLoadingNewSteps = ref(false)

function updatedDataWithStepsArray() {
  dataWithStepsPagination.value = []
  dataWithSteps.value = []
  if (props.userHealthStepsPagination) {
    for (const data of props.userHealthStepsPagination) {
      if (data.steps) {
        dataWithStepsPagination.value.push(data)
      }
    }
  }
  if (props.userHealthSteps) {
    for (const data of props.userHealthSteps) {
      if (data.steps) {
        dataWithSteps.value.push(data)
      }
    }
  }
}

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

watchEffect(() => {
  if (props.userHealthStepsPagination) {
    updatedDataWithStepsArray()
  }
})

onMounted(() => {
  updatedDataWithStepsArray()
})
</script>