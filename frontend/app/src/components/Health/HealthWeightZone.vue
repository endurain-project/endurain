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
        data-bs-target="#addWeightModal"
        >{{ $t('healthWeightZoneComponent.buttonAddWeight') }}</a
      >

      <HealthWeightAddEditModalComponent
        :action="'add'"
        @isLoadingNewWeight="updateIsLoadingNewWeight"
        @createdWeight="updateWeightListAdded"
      />

      <!-- Checking if dataWithWeight is loaded and has length -->
      <div
        v-if="dataWithWeight && dataWithWeight.length"
        class="mt-3 p-3 bg-body-tertiary rounded shadow-sm"
      >
        <!-- show graph -->
        <HealthWeightLineChartComponent :userHealthWeight="dataWithWeight" :isLoading="isLoading" />

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
          v-for="data in dataWithWeightPagination"
          :key="data.id"
          :data="data"
        >
          <HealthWeightListComponent
            :data="data"
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
      <div v-else class="mt-3">
        <br />
        <NoItemsFoundComponent />
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, watchEffect, onMounted } from 'vue'
import HealthWeightAddEditModalComponent from './HealthWeightZone/HealthWeightAddEditModalComponent.vue'
import HealthWeightLineChartComponent from './HealthWeightZone/HealthWeightLineChartComponent.vue'
import HealthWeightListComponent from './HealthWeightZone/HealthWeightListComponent.vue'
import LoadingComponent from '../GeneralComponents/LoadingComponent.vue'
import NoItemsFoundComponent from '../GeneralComponents/NoItemsFoundComponents.vue'
import PaginationComponent from '../GeneralComponents/PaginationComponent.vue'

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

const emit = defineEmits(['createdWeight', 'deletedWeight', 'editedWeight', 'pageNumberChanged'])

const dataWithWeight = ref([])
const dataWithWeightPagination = ref([])
const isLoadingNewWeight = ref(false)

function updatedDataWithWeightArray() {
  dataWithWeightPagination.value = []
  dataWithWeight.value = []
  if (props.userHealthWeightPagination) {
    for (const data of props.userHealthWeightPagination) {
      if (data.weight) {
        dataWithWeightPagination.value.push(data)
      }
    }
  }
  if (props.userHealthWeight) {
    for (const data of props.userHealthWeight) {
      if (data.weight) {
        dataWithWeight.value.push(data)
      }
    }
  }
}

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

watchEffect(() => {
  if (props.userHealthWeightPagination) {
    updatedDataWithWeightArray()
  }
})

onMounted(() => {
  updatedDataWithWeightArray()
})
</script>
