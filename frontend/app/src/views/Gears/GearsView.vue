<template>
  <h1>{{ $t('gearsView.title') }}</h1>
  <div class="row row-gap-3">
    <div class="col-lg-4 col-md-12">
      <div class="p-3 bg-body-tertiary rounded shadow-sm">
        <!-- Add gear zone -->
        <p>{{ $t('gearsView.buttonAddGear') }}</p>
        <a
          class="w-100 btn btn-primary"
          href="#"
          role="button"
          data-bs-toggle="modal"
          data-bs-target="#addGearModal"
        >
          {{ $t('gearsView.buttonAddGear') }}
        </a>

        <!-- Add gear modal -->
        <GearsAddEditUserModalComponent
          :action="'add'"
          @createdGear="addGearList"
          @isLoadingNewGear="setIsLoadingNewGear"
        />

        <!-- Search gear by nickname zone -->
        <br />
        <p class="mt-2">{{ $t('gearsView.subTitleSearchGearByNickname') }}</p>
        <form>
          <div class="mb-3">
            <input
              class="form-control"
              type="text"
              name="gearNickname"
              :placeholder="$t('gearsView.placeholderSearchGearByNickname')"
              v-model="searchNickname"
              required
            />
          </div>
        </form>
      </div>
    </div>
    <div class="col">
      <div v-if="isLoading">
        <LoadingComponent />
      </div>
      <div v-else>
        <!-- Checking if userGears is loaded and has length -->
        <div v-if="userGears && userGears.length" class="p-3 bg-body-tertiary rounded shadow-sm">
          <!-- Iterating over userGears to display them -->
          <span class="mb-1"
            >{{ $t('gearsView.displayUserNumberOfGears1') }}{{ userGearsNumber
            }}{{ $t('gearsView.displayUserNumberOfGears2') }}{{ userGears.length
            }}{{ $t('gearsView.displayUserNumberOfGears3') }}</span
          >

          <!-- Displaying loading new gear if applicable -->
          <ul class="list-group list-group-flush" v-if="isLoadingNewGear">
            <li class="list-group-item rounded">
              <LoadingComponent />
            </li>
          </ul>

          <!-- Displaying loading if gears are updating -->
          <LoadingComponent v-if="isGearsUpdatingLoading" />

          <!-- List gears -->
          <ul class="list-group list-group-flush" v-for="gear in userGears" :key="gear.id" v-else>
            <GearsListComponent
              :gear="gear"
              @editedGear="editGearList"
              @gearDeleted="updateGearListOnDelete"
            />
          </ul>

          <!-- pagination area -->
          <PaginationComponent
            :totalPages="totalPages"
            :pageNumber="pageNumber"
            @pageNumberChanged="setPageNumber"
            v-if="!searchNickname"
          />
        </div>
        <!-- Displaying a message or component when there are no activities -->
        <NoItemsFoundComponent v-else />
      </div>
    </div>
  </div>
  <!-- back button -->
  <BackButtonComponent />
</template>

<script setup>
// Importing the vue composition API
import { ref, onMounted, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRoute } from 'vue-router'
// import lodash
import { debounce } from 'lodash'
// Import Notivue push
import { push } from 'notivue'
// Importing the components
import NoItemsFoundComponent from '@/components/GeneralComponents/NoItemsFoundComponents.vue'
import LoadingComponent from '@/components/GeneralComponents/LoadingComponent.vue'
import BackButtonComponent from '@/components/GeneralComponents/BackButtonComponent.vue'
import PaginationComponent from '@/components/GeneralComponents/PaginationComponent.vue'
import GearsAddEditUserModalComponent from '@/components/Gears/GearsAddEditGearModalComponent.vue'
import GearsListComponent from '@/components/Gears/GearsListComponent.vue'
// Importing the services
import { gears } from '@/services/gearsService'
// Importing the stores
import { useServerSettingsStore } from '@/stores/serverSettingsStore'

const { t } = useI18n()
const serverSettingsStore = useServerSettingsStore()
const route = useRoute()
const isLoading = ref(true)
const isGearsUpdatingLoading = ref(true)
const isLoadingNewGear = ref(false)
const userGears = ref([])
const userGearsNumber = ref(0)
const pageNumber = ref(1)
const totalPages = ref(1)
const numRecords = serverSettingsStore.serverSettings.num_records_per_page || 25
const searchNickname = ref('')

const performSearch = debounce(async () => {
  // If the search nickname is empty, reset the list to initial state.
  if (!searchNickname.value) {
    // Reset the list to the initial state when search text is cleared
    pageNumber.value = 1
    // Fetch gears
    await fetchGears()
    // Exit the function
    return
  }
  try {
    // Fetch the users based on the search nickname.
    userGears.value = await gears.getGearContainsNickname(searchNickname.value)
  } catch (error) {
    push.error(`${t('gearsView.errorGearNotFound')} - ${error}`)
  }
}, 500)

function setPageNumber(page) {
  // Set the page number.
  pageNumber.value = page
}

async function updateGears() {
  try {
    // Set the loading variable to true.
    isGearsUpdatingLoading.value = true

    // Fetch the gears with pagination.
    userGears.value = await gears.getUserGearsWithPagination(pageNumber.value, numRecords)

    // Set the loading variable to false.
    isGearsUpdatingLoading.value = false
  } catch (error) {
    // If there is an error, set the error message and show the error alert.
    push.error(`${t('gearsView.errorFetchingGears')} - ${error}`)
  }
}

async function fetchGears() {
  try {
    // Get the total number of user gears.
    userGearsNumber.value = await gears.getUserGearsNumber()

    // Fetch the gears with pagination.
    await updateGears()

    // Update total pages
    totalPages.value = Math.ceil(userGearsNumber.value / numRecords)
  } catch (error) {
    // If there is an error, set the error message and show the error alert.
    push.error(`${t('gearsView.errorFetchingGears')} - ${error}`)
  }
}

onMounted(async () => {
  if (route.query.gearDeleted === 'true') {
    // Set the gearDeleted value to true and show the success alert.
    push.success(t('gearsView.successGearDeleted'))
  }

  if (route.query.gearFound === 'false') {
    // Set the gearFound value to false and show the error alert.
    push.error(`${t('gearsView.errorGearNotFound')} - ID:${route.query.id}`)
  }

  // Fetch gears
  await fetchGears()

  // Set the isLoading variables to false.
  isGearsUpdatingLoading.value = false
  isLoading.value = false
})

function addGearList(createdGear) {
  userGears.value.unshift(createdGear)
  userGearsNumber.value++
}

function editGearList(editedGear) {
  const index = userGears.value.findIndex((gear) => gear.id === editedGear.id)
  userGears.value[index] = editedGear
}

function setIsLoadingNewGear(state) {
  isLoadingNewGear.value = state
}

function updateGearListOnDelete(gearDeletedId) {
  userGears.value = userGears.value.filter((gear) => gear.id !== gearDeletedId)
  userGearsNumber.value--
}

// Watch the search nickname variable.
watch(searchNickname, performSearch, { immediate: false })

// Watch the page number variable.
watch(pageNumber, updateGears, { immediate: false })
</script>
