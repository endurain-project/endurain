<template>
  <div v-if="isLoading">
    <LoadingComponent />
  </div>
  <h1 v-else>{{ gear?.nickname }}</h1>

  <div class="row row-gap-3 mt-4">
    <!-- left column -->
    <div class="col-lg-3 col-md-12">
      <div class="bg-body-tertiary p-3 rounded shadow-sm">
        <!-- Gear photo -->
        <div v-if="isLoading">
          <LoadingComponent />
        </div>
        <div v-else>
          <div class="justify-content-center align-items-center d-flex">
            <img
              :src="getGearAvatar(gear?.gear_type)"
              :alt="
                $t(
                  `gearView.gearTypeOption${
                    gear?.gear_type >= 1 && gear?.gear_type <= 8 ? gear?.gear_type : 8
                  }`
                ) + ' avatar'
              "
              width="180"
              height="180"
              class="rounded-circle"
            />
          </div>
          <br />
          <div class="vstack justify-content-center align-items-center d-flex">
            <!-- badges  -->
            <div class="hstack justify-content-center">
              <span
                class="badge bg-success-subtle border border-success-subtle text-success-emphasis align-middle"
                v-if="gear?.active == true"
              >
                {{ $t('gearView.gearIsActiveBadge') }}
              </span>
              <span
                class="badge bg-danger-subtle border border-danger-subtle text-danger-emphasis align-middle"
                v-else
              >
                {{ $t('gearView.gearIsInactiveBadge') }}
              </span>
              <span
                class="ms-2 badge bg-primary-subtle border border-primary-subtle text-primary-emphasis align-middle"
              >
                {{
                  $t(
                    `gearView.gearTypeOption${gear?.gear_type >= 1 && gear?.gear_type <= 8 ? gear?.gear_type : 8}`
                  )
                }}
              </span>
              <span
                class="ms-2 badge bg-primary-subtle border border-primary-subtle text-primary-emphasis align-middle"
                v-if="gear?.strava_gear_id"
              >
                {{ $t('gearView.gearFromStrava') }}
              </span>
              <span
                class="ms-2 badge bg-primary-subtle border border-primary-subtle text-primary-emphasis align-middle"
                v-if="gear?.garminconnect_gear_id"
              >
                {{ $t('gearView.gearFromGarminConnect') }}
              </span>
            </div>
          </div>
          <!-- add component zone -->
          <button
            type="button"
            class="mt-2 w-100 btn btn-primary"
            data-bs-toggle="modal"
            data-bs-target="#addGearComponentModal"
            :disabled="![1, 2, 4, 7].includes(gear?.gear_type)"
          >
            {{ $t('gearView.buttonAddComponent') }}
          </button>

          <!-- add component modal -->
          <GearComponentAddEditModalComponent
            :action="'add'"
            :gear="gear"
            @createdGearComponent="addGearComponentList"
            @isLoadingNewGearComponent="setIsLoadingNewGearComponent"
          />

          <hr />

          <!-- edit gear zone -->
          <button
            type="button"
            class="w-100 btn btn-primary"
            data-bs-toggle="modal"
            :data-bs-target="`#editGearModal${gear?.id}`"
          >
            {{ $t('gearView.buttonEditGear') }}
          </button>

          <!-- edit gear modal -->
          <GearsAddEditGearModalComponent
            :action="'edit'"
            :gear="gear"
            @editedGear="editGearList"
          />

          <button
            type="button"
            class="mt-2 w-100 btn btn-danger"
            data-bs-toggle="modal"
            data-bs-target="#deleteGearModal"
          >
            {{ $t('gearView.buttonDeleteGear') }}
          </button>

          <!-- Modal delete gear -->
          <ModalComponent
            modalId="deleteGearModal"
            :title="t('gearView.buttonDeleteGear')"
            :body="`${t('gearView.modalDeleteGearBody1')} <b>${gear?.nickname}</b>?<br>${t('gearView.modalDeleteGearBody2')}`"
            :actionButtonType="`danger`"
            :actionButtonText="t('gearView.buttonDeleteGear')"
            @submitAction="submitDeleteGear"
          />

          <hr />

          <!-- details  -->
          <div class="vstack align-items-center">
            <span class="mt-2" v-if="gear?.gear_type !== 4">
              <strong> {{ $t('gearView.labelDistance') }}: </strong>
              <span v-if="authStore?.user?.units === 'metric'">
                {{ gearDistance }} {{ $t('generalItems.unitsKm') }}</span
              >
              <span v-else> {{ kmToMiles(gearDistance) }} {{ $t('generalItems.unitsMiles') }}</span>
            </span>
            <span v-else>
              <strong> {{ $t('gearView.labelTime') }}: </strong>
              <span>{{ formatSecondsToMinutes(gearTime) }}</span>
            </span>
            <span class="mt-2" v-if="gear?.brand"
              ><strong>{{ $t('gearView.labelBrand') }}:</strong> {{ gear?.brand }}</span
            >
            <span class="mt-2" v-if="gear?.model"
              ><strong>{{ $t('gearView.labelModel') }}:</strong> {{ gear?.model }}</span
            >
            <div class="mt-2" v-if="gear?.purchase_value">
              <span class="me-1"
                ><strong>{{ $t('gearView.labelPurchaseValue') }}:</strong>
                {{ gear?.purchase_value }}</span
              >
              <span v-if="authStore.user.currency === 'euro'">{{
                $t('generalItems.currencyEuroSymbol')
              }}</span>
              <span v-else-if="authStore.user.currency === 'dollar'">{{
                $t('generalItems.currencyDollarSymbol')
              }}</span>
              <span v-else>{{ $t('generalItems.currencyPoundSymbol') }}</span>
            </div>
            <div class="mt-2">
              <span class="me-1"
                ><strong>{{ $t('gearView.labelTotalCost') }}:</strong> {{ gearTotalValue }}</span
              >
              <span v-if="authStore.user.currency === 'euro'">{{
                $t('generalItems.currencyEuroSymbol')
              }}</span>
              <span v-else-if="authStore.user.currency === 'dollar'">{{
                $t('generalItems.currencyDollarSymbol')
              }}</span>
              <span v-else>{{ $t('generalItems.currencyPoundSymbol') }}</span>
            </div>
          </div>
        </div>
      </div>
    </div>
    <div class="col-lg-5">
      <div v-if="isLoading">
        <LoadingComponent />
      </div>
      <div v-else class="bg-body-tertiary p-3 rounded shadow-sm">
        <div class="hstack align-items-baseline justify-content-between">
          <div class="d-flex align-items-baseline">
            <h5>{{ $t('gearView.titleComponents') }}</h5>
            <span class="mb-1 ms-1" v-if="filterValues.showInactive"
              >({{ gearComponents.length }})</span
            >
            <span class="mb-1 ms-1" v-else>({{ gearComponentsActive.length }})</span>
          </div>
          <FilterDropdownComponent
            :options="filterOptions"
            v-model="filterValues"
            :aria-label="$t('generalItems.filterOptions')"
          />
        </div>

        <NoItemsFoundComponent
          :showShadow="false"
          v-if="!gearComponents || (gearComponents && gearComponents.length == 0)"
        />
        <div v-else>
          <!-- Displaying loading new gear component if applicable -->
          <ul class="list-group list-group-flush" v-if="isLoadingNewGearComponent">
            <li class="list-group-item rounded">
              <LoadingComponent />
            </li>
          </ul>
          <!-- List gear components-->
          <ul
            class="list-group list-group-flush"
            v-for="gearComponent in filterValues.showInactive
              ? gearComponents
              : gearComponentsActive"
            :key="gearComponent.id"
          >
            <GearComponentListComponent
              :gear="gear"
              :gearActivities="gearActivities"
              :gearComponent="gearComponent"
              @createdGearComponent="addGearComponentList"
              @editedGearComponent="editGearComponentList"
              @gearComponentDeleted="updateGearComponentListOnDelete"
            />
          </ul>
        </div>
      </div>
    </div>
    <div class="col">
      <div v-if="isLoading">
        <LoadingComponent />
      </div>
      <div v-else class="bg-body-tertiary p-3 rounded shadow-sm">
        <div class="hstack align-items-baseline">
          <h5>
            {{ $t('gearView.title') }}
          </h5>
          <span class="mb-1 ms-1" v-if="gearActivitiesWithPagination"
            >({{ gearActivitiesWithPagination.length }}{{ $t('generalItems.ofWithSpaces')
            }}{{ gearActivitiesNumber }})</span
          >
        </div>

        <div v-if="isLoadingGearActivities">
          <LoadingComponent />
        </div>
        <div v-else>
          <NoItemsFoundComponent
            :showShadow="false"
            v-if="
              !gearActivitiesWithPagination ||
              (gearActivitiesWithPagination && gearActivitiesWithPagination.length == 0)
            "
          />
          <div v-else>
            <ul
              class="list-group list-group-flush mb-1"
              v-for="activity in gearActivitiesWithPagination"
              :key="activity.id"
              :activity="activity"
            >
              <li
                class="vstack list-group-item d-flex justify-content-between bg-body-tertiary ps-0"
              >
                <router-link
                  :to="{ name: 'activity', params: { id: activity.id } }"
                  class="link-body-emphasis link-underline-opacity-0 link-underline-opacity-100-hover"
                >
                  <span v-if="activity.name === 'Workout'">{{ formatName(activity, t) }}</span>
                  <span v-else>{{ activity.name }}</span>
                </router-link>
                <span
                  >{{ formatDateMed(activity.start_time_tz_applied) }} @
                  {{ formatTime(activity.start_time_tz_applied) }}</span
                >
              </li>
            </ul>

            <!-- pagination area -->
            <PaginationComponent
              :totalPages="totalPages"
              :pageNumber="pageNumber"
              @pageNumberChanged="setPageNumber"
            />
          </div>
        </div>
      </div>
    </div>
  </div>

  <!-- back button -->
  <BackButtonComponent />
</template>

<script setup>
import { ref, computed, onMounted, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRoute, useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/authStore'
import { useServerSettingsStore } from '@/stores/serverSettingsStore'
import { push } from 'notivue'
import NoItemsFoundComponent from '@/components/GeneralComponents/NoItemsFoundComponents.vue'
import LoadingComponent from '@/components/GeneralComponents/LoadingComponent.vue'
import BackButtonComponent from '@/components/GeneralComponents/BackButtonComponent.vue'
import ModalComponent from '@/components/Modals/ModalComponent.vue'
import FilterDropdownComponent from '@/components/GeneralComponents/FilterDropdownComponent.vue'
import GearsAddEditGearModalComponent from '@/components/Gears/GearsAddEditGearModalComponent.vue'
import GearComponentListComponent from '@/components/Gears/GearComponentListComponent.vue'
import GearComponentAddEditModalComponent from '@/components/Gears/GearComponentAddEditModalComponent.vue'
import PaginationComponent from '@/components/GeneralComponents/PaginationComponent.vue'
import { gears } from '@/services/gearsService'
import { gearsComponents } from '@/services/gearsComponentsService'
import { activities } from '@/services/activitiesService'
import { formatDateMed, formatTime, formatSecondsToMinutes } from '@/utils/dateTimeUtils'
import { kmToMiles } from '@/utils/unitsUtils'
import { formatName } from '@/utils/activityUtils'
import { getGearAvatar } from '@/constants/gearAvatarConstants'

const { t } = useI18n()
const authStore = useAuthStore()
const serverSettingsStore = useServerSettingsStore()
const route = useRoute()
const router = useRouter()
const isLoading = ref(true)
const isLoadingGearActivities = ref(true)
const isLoadingNewGearComponent = ref(false)
const pageNumber = ref(1)
const totalPages = ref(1)
const numRecords = serverSettingsStore.serverSettings.num_records_per_page || 25
const gear = ref(null)
const gearActivitiesNumber = ref(0)
const gearActivitiesWithPagination = ref([])
const gearActivities = ref([])
const gearDistance = ref(0)
const gearTime = ref(0)
const gearComponents = ref(null)
const gearComponentsActive = ref(null)
const filterValues = ref({
  showInactive: false
})
const filterOptions = computed(() => [
  { id: 'showInactive', label: t('gearView.showInactiveComponents') }
])
const gearComponentsTotalValue = ref(0)
const gearTotalValue = ref(0)

async function submitDeleteGear() {
  try {
    gear.value = await gears.deleteGear(route.params.id)
    return router.push({ path: '/gears', query: { gearDeleted: 'true' } })
  } catch (error) {
    push.error(`${t('gearView.errorGearDelete')} - ${error}`)
  }
}

function editGearList(editedGear) {
  gear.value = editedGear
  updateTotalCosts()
}

function setPageNumber(page) {
  // Set the page number.
  pageNumber.value = page
}

function setIsLoadingNewGearComponent(state) {
  isLoadingNewGearComponent.value = state
}

function addGearComponentList(createdGearComponent) {
  gearComponents.value.unshift(createdGearComponent)
  updateGearComponentsActive()
  updateTotalCosts()
}

function editGearComponentList(editedGearComponent) {
  const index = gearComponents.value.findIndex(
    (gearComponent) => gearComponent.id === editedGearComponent.id
  )
  gearComponents.value[index] = editedGearComponent
  updateGearComponentsActive()
  updateTotalCosts()
}

function updateGearComponentListOnDelete(gearComponentDeletedId) {
  gearComponents.value = gearComponents.value.filter(
    (gearComponent) => gearComponent.id !== gearComponentDeletedId
  )
  updateTotalCosts()
}

async function updateGearActivities() {
  try {
    isLoadingGearActivities.value = true
    gearActivities.value = await activities.getUserActivitiesByGearId(route.params.id)
    gearActivitiesNumber.value = await activities.getUserActivitiesByGearIdNumber(route.params.id)
    gearActivitiesWithPagination.value = await activities.getUserActivitiesByGearIdWithPagination(
      route.params.id,
      pageNumber.value,
      numRecords
    )
    // Update total pages
    totalPages.value = Math.ceil(gearActivitiesNumber.value / numRecords)
  } catch (error) {
    push.error(`${t('gearView.errorFetchingGears')} - ${error}`)
  } finally {
    isLoadingGearActivities.value = false
  }
}

function updateGearComponentsActive() {
  gearComponentsActive.value = gearComponents.value.filter(
    (gearComponent) => gearComponent.active === true
  )
  updateTotalCosts()
}

function updateTotalCosts() {
  gearComponentsTotalValue.value = 0
  for (const gearComponent of gearComponents.value) {
    if (gearComponent.purchase_value) {
      gearComponentsTotalValue.value += gearComponent.purchase_value
    }
  }
  if (!gear.value.purchase_value) {
    gearTotalValue.value = gearComponentsTotalValue.value
    return
  }
  gearTotalValue.value = gear.value.purchase_value + gearComponentsTotalValue.value
}

onMounted(async () => {
  try {
    gear.value = await gears.getGearById(route.params.id)
    if (!gear.value) {
      return router.push({
        path: '/gears',
        query: { gearFound: 'false', id: route.params.id }
      })
    }
    await updateGearActivities()
    if (gearActivities.value) {
      for (const activity of gearActivities.value) {
        gearDistance.value += activity.distance
        gearTime.value += activity.total_timer_time || 0
      }
      gearDistance.value = (gearDistance.value / 1000).toFixed(2)
    }
    gearDistance.value = Math.floor(Number(gearDistance.value) + gear.value.initial_kms)

    gearComponents.value = await gearsComponents.getGearComponentsByGearId(route.params.id)
    updateGearComponentsActive()
    updateTotalCosts()
  } catch (error) {
    if (error.toString().includes('422')) {
      return router.push({
        path: '/gears',
        query: { gearFound: 'false', id: route.params.id }
      })
    }
    push.error(`${t('gearView.errorFetchingGears')} - ${error}`)
  }
  isLoading.value = false
})

// Watch the page number variable.
watch(pageNumber, updateGearActivities, { immediate: false })
</script>
