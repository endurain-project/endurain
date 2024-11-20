<template>
    <h1>{{ $t("gearsView.title") }}</h1>
    <div class="row row-gap-3">
        <div class="col-lg-4 col-md-12">
            <!-- Add gear zone -->
            <p>{{ $t("gearsView.buttonAddGear") }}:</p>
            <a class="w-100 btn btn-primary" href="#" role="button" data-bs-toggle="modal" data-bs-target="#addGearModal">
                {{ $t("gearsView.buttonAddGear") }}
            </a>

            <!-- Add gear modal -->
            <div class="modal fade" id="addGearModal" tabindex="-1" aria-labelledby="addGearModal" aria-hidden="true">
                <div class="modal-dialog">
                    <div class="modal-content">
                        <div class="modal-header">
                            <h1 class="modal-title fs-5" id="addGearModal">{{ $t("gearsView.buttonAddGear") }}</h1>
                            <!--<button type="button" class="btn-close" data-bs-dismiss="modal" aria-label="Close"></button>-->
                        </div>
                        <form @submit.prevent="submitAddGearForm">
                            <div class="modal-body">
                                <!-- brand fields -->
                                <label for="gearBrandAdd"><b>{{ $t("gearsView.modalBrand") }}:</b></label>
                                <input class="form-control" type="text" name="gearBrandAdd" :placeholder='$t("gearsView.modalBrand")' v-model="brand" maxlength="250">
                                <!-- model fields -->
                                <label for="gearModelAdd"><b>{{ $t("gearsView.modalModel") }}:</b></label>
                                <input class="form-control" type="text" name="gearModelAdd" :placeholder='$t("gearsView.modalModel")' v-model="model" maxlength="250">
                                <!-- nickname fields -->
                                <label for="gearNicknameAdd"><b>* {{ $t("gearsView.modalNickname") }}:</b></label>
                                <input class="form-control" type="text" name="gearNicknameAdd" :placeholder='$t("gearsView.modalNickname")' v-model="nickname" maxlength="250" required>
                                <!-- gear type fields -->
                                <label for="gearTypeAdd"><b>* {{ $t("gearsView.modalGearTypeLabel") }}:</b></label>
                                <select class="form-control" name="gearTypeAdd" v-model="gearType" required>
                                    <option value="1">{{ $t("gearsView.modalGearTypeOption1Bike") }}</option>
                                    <option value="2">{{ $t("gearsView.modalGearTypeOption2Shoes") }}</option>
                                    <option value="3">{{ $t("gearsView.modalGearTypeOption3Wetsuit") }}</option>
                                </select>
                                <!-- date fields -->
                                <label for="gearDateAdd"><b>* {{ $t("gearsView.modalDateLabel") }}:</b></label>
                                <input class="form-control" type="date" name="gearDateAdd" :placeholder='$t("gearsView.modalDatePlaceholder")' v-model="date" required>
                                <p>* {{ $t("generalItems.requiredField") }}</p>
                            </div>
                            <div class="modal-footer">
                                <button type="button" class="btn btn-secondary" data-bs-dismiss="modal">{{ $t("generalItems.buttonClose") }}</button>
                                <button type="submit" class="btn btn-success" name="addGear" data-bs-dismiss="modal">{{ $t("gearsView.buttonAddGear") }}</button>
                            </div>
                        </form>
                    </div>
                </div>
            </div>

            <!-- Search gear by nickname zone -->
            <br>
            <p class="mt-2">{{ $t("gearsView.subTitleSearchGearByNickname") }}:</p>
            <form>
                <div class="mb-3">
                    <input class="form-control" type="text" name="gearNickname" :placeholder='$t("gearsView.placeholderSearchGearByNickname")' v-model="searchNickname" required>
                </div>
            </form>
        </div>
        <div class="col">
            <div v-if="isLoading">
                <LoadingComponent />
            </div>
            <div v-else>
                <!-- Checking if userGears is loaded and has length -->
                <div v-if="userGears && userGears.length">
                    <!-- Iterating over userGears to display them -->
                    <p>{{ $t("gearsView.displayUserNumberOfGears1") }}{{ userGearsNumber }}{{ $t("gearsView.displayUserNumberOfGears2") }}{{ userGears.length }}{{ $t("gearsView.displayUserNumberOfGears3") }}</p>

                    <!-- Displaying loading new gear if applicable -->
                    <ul class="list-group list-group-flush" v-if="isLoadingNewGear">
                        <li class="list-group-item rounded">
                            <LoadingComponent />
                        </li>
                    </ul>

                    <!-- Displaying loading if gears are updating -->
                    <LoadingComponent v-if="isGearsUpdatingLoading"/>

                    <!-- List gears -->
                    <ul class="list-group list-group-flush" v-for="gear in userGears" :key="gear.id" :gear="gear" v-else>
                        <li class="list-group-item d-flex justify-content-between">
                            <div class="d-flex align-items-center">
                                <img src="/src/assets/avatar/bicycle1.png" alt="Bycicle avatar" width="55" height="55" v-if="gear.gear_type == 1">
                                <img src="/src/assets/avatar/running_shoe1.png" alt="Bycicle avatar" width="55" height="55" v-else-if="gear.gear_type == 2">
                                <img src="/src/assets/avatar/wetsuit1.png" alt="Bycicle avatar" width="55" height="55" v-else>
                                <div class="ms-3">
                                    <div class="fw-bold">
                                        <router-link :to="{ name: 'gear', params: { id: gear.id }}" class="link-body-emphasis link-underline-opacity-0 link-underline-opacity-100-hover">
                                            {{ gear.nickname }}
                                        </router-link>
                                    </div>
                                    <b>{{ $t("gearsView.gearTypeLabel") }}</b>
                                    <span v-if="gear.gear_type == 1">{{ $t("gearsView.gearTypeOption1") }}</span>
                                    <span v-else-if="gear.gear_type == 2">{{ $t("gearsView.gearTypeOption2") }}</span>
                                    <span v-else>{{ $t("gearsView.gearTypeOption3") }}</span>
                                    <br>
                                </div>
                            </div>
                            <div>
                                <!--<span class="badge bg-success-subtle border border-success-subtle text-success-emphasis align-middle" v-if="gear.is_active == 1">{{ $t("gearsView.activeState") }}</span>-->
                                <span class="badge bg-danger-subtle border border-danger-subtle text-danger-emphasis align-middle" v-if="gear.is_active == 0">{{ $t("gearsView.inactiveState") }}</span>
                                <span class="badge bg-primary-subtle border border-primary-subtle text-primary-emphasis align-middle ms-2" v-if="gear.strava_gear_id">{{ $t("gearsView.gearFromStrava") }}</span>
                                <span class="badge bg-primary-subtle border border-primary-subtle text-primary-emphasis align-middle ms-2" v-if="gear.garminconnect_gear_id">{{ $t("gearsView.gearFromGarminConnect") }}</span>
                            </div>
                        </li>
                    </ul>

                    <!-- pagination area -->
                    <PaginationComponent :totalPages="totalPages" :pageNumber="pageNumber" @pageNumberChanged="setPageNumber" v-if="!searchNickname"/>
                </div>
                <!-- Displaying a message or component when there are no activities -->
                <NoItemsFoundComponent v-else />
            </div>

        </div>
    </div>
    <!-- back button -->
    <BackButtonComponent />
</template>

<script>
// Importing the vue composition API
import { ref, onMounted, watch } from 'vue';
import { useI18n } from 'vue-i18n';
import { useRoute } from 'vue-router';
// import lodash
import { debounce } from 'lodash';
// Import Notivue push
import { push } from "notivue";
// Importing the components
import NoItemsFoundComponent from '@/components/GeneralComponents/NoItemsFoundComponents.vue';
import LoadingComponent from '@/components/GeneralComponents/LoadingComponent.vue';
import BackButtonComponent from '@/components/GeneralComponents/BackButtonComponent.vue';
import PaginationComponent from '@/components/GeneralComponents/PaginationComponent.vue';
// Importing the services
import { gears } from '@/services/gearsService';

//import { Modal } from 'bootstrap';

export default {
    components: {
        NoItemsFoundComponent,
        LoadingComponent,
        PaginationComponent,
        BackButtonComponent,
    },
    setup() {
        const { t } = useI18n();
        const route = useRoute();
        const brand = ref('');
        const model = ref('');
        const nickname = ref('');
        const gearType = ref(1);
        const date = ref(null);
        const isLoading = ref(true);
        const isGearsUpdatingLoading = ref(true);
        const isLoadingNewGear = ref(false)
        const userGears = ref([]);
        const userGearsNumber = ref(0);
        const pageNumber = ref(1);
        const totalPages = ref(1);
        const numRecords = 5;
        const searchNickname = ref('');

        const performSearch = debounce(async () => {
            // If the search nickname is empty, reset the list to initial state.
            if (!searchNickname.value) {
                // Reset the list to the initial state when search text is cleared
                pageNumber.value = 1;
                // Fetch gears
                await fetchGears();
                // Exit the function
                return;
            }
            try {
                // Fetch the users based on the search nickname.
                userGears.value = await gears.getGearByNickname(searchNickname.value);
            } catch (error) {
				push.error(`${t("gearsView.errorGearNotFound")} - ${error}`);
            }
        }, 500);
        
        async function submitAddGearForm() {
            // Set the isLoadingNewGear variable to true.
            isLoadingNewGear.value = true;
            try {
                // Create the gear data object.
                const data = {
                    brand: brand.value,
                    model: model.value,
                    nickname: nickname.value,
                    gear_type: gearType.value,
                    created_at: date.value,
                };

                // Create the gear and get the created gear id.
                const createdGearId = await gears.createGear(data);

                // Get the created gear and add it to the userGears array.
                const newGear = await gears.getGearById(createdGearId);
                userGears.value.unshift(newGear);

                userGearsNumber.value++;

                // Set the success message and show the success alert.
                push.success(t("gearsView.successGearAdded"));
            } catch (error) {
                // If there is an error, set the error message and show the error alert.
				push.error(`${t("generalItems.errorFetchingInfo")} - ${error}`);
            } finally {
                // Set the isLoadingNewGear variable to false.
                isLoadingNewGear.value = false;
            }
        }

        function setPageNumber(page) {
            // Set the page number.
            pageNumber.value = page;
        }

        async function updateGears() {
            try {
                // Set the loading variable to true.
                isGearsUpdatingLoading.value = true;

                // Fetch the gears with pagination.
                userGears.value = await gears.getUserGearsWithPagination(pageNumber.value, numRecords);

                // Set the loading variable to false.
                isGearsUpdatingLoading.value = false;
            } catch (error) {
                // If there is an error, set the error message and show the error alert.
				push.error(`${t("generalItems.errorFetchingInfo")} - ${error}`);
            }
        }

        async function fetchGears() {
            try {
                // Get the total number of user gears.
                userGearsNumber.value = await gears.getUserGearsNumber();

                // Fetch the gears with pagination.
                await updateGears();

                // Update total pages
                totalPages.value = Math.ceil(userGearsNumber.value / numRecords);
            } catch (error) {
                // If there is an error, set the error message and show the error alert.
				push.error(`${t("generalItems.errorFetchingInfo")} - ${error}`);
            }
        }

        onMounted(async () => {
            if (route.query.gearDeleted === 'true') {
                // Set the gearDeleted value to true and show the success alert.
                push.success(t("gearsView.successGearDeleted"));
            }

            if (route.query.gearFound === 'false') {
                // Set the gearFound value to false and show the error alert.
				push.error(`${t("gearsView.errorGearNotFound")} - ${error}`);
            }

            // Fetch gears
            await fetchGears();

            // Set the isLoading variables to false.
            isGearsUpdatingLoading.value = false;
            isLoading.value = false;
        });
        
        // Watch the search nickname variable.
        watch(searchNickname, performSearch, { immediate: false });

        // Watch the page number variable.
        watch(pageNumber, updateGears, { immediate: false });

        return {
            brand,
            model,
            nickname,
            totalPages,
            pageNumber,
            numRecords,
            gearType,
            date,
            isLoading,
            isGearsUpdatingLoading,
            isLoadingNewGear,
            userGears,
            userGearsNumber,
            searchNickname,
            t,
            submitAddGearForm,
            setPageNumber,
        };
    },
};
</script>