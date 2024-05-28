<template>
    <h1>{{ $t("gears.title") }}</h1>
    <div class="row row-gap-3">
        <div class="col-lg-4 col-md-12">
            <!-- Add gear zone -->
            <p>{{ $t("gears.buttonAddGear") }}:</p>
            <a class="w-100 btn btn-primary" href="#" role="button" data-bs-toggle="modal" data-bs-target="#addGearModal">
                {{ $t("gears.buttonAddGear") }}
            </a>

            <!-- Add gear modal -->
            <div class="modal fade" id="addGearModal" tabindex="-1" aria-labelledby="addGearModal" aria-hidden="true">
                <div class="modal-dialog">
                    <div class="modal-content">
                        <div class="modal-header">
                            <h1 class="modal-title fs-5" id="addGearModal">{{ $t("gears.buttonAddGear") }}</h1>
                            <!--<button type="button" class="btn-close" data-bs-dismiss="modal" aria-label="Close"></button>-->
                        </div>
                        <form @submit.prevent="submitAddGearForm">
                            <div class="modal-body">
                                <!-- brand fields -->
                                <label for="gearBrandAdd"><b>{{ $t("gears.modalBrand") }}:</b></label>
                                <input class="form-control" type="text" name="gearBrandAdd" :placeholder='$t("gears.modalBrand")' v-model="brand" maxlength="250">
                                <!-- model fields -->
                                <label for="gearModelAdd"><b>{{ $t("gears.modalModel") }}:</b></label>
                                <input class="form-control" type="text" name="gearModelAdd" :placeholder='$t("gears.modalModel")' v-model="model" maxlength="250">
                                <!-- nickname fields -->
                                <label for="gearNicknameAdd"><b>* {{ $t("gears.modalNickname") }}:</b></label>
                                <input class="form-control" type="text" name="gearNicknameAdd" :placeholder='$t("gears.modalNickname")' v-model="nickname" maxlength="250" required>
                                <!-- gear type fields -->
                                <label for="gearTypeAdd"><b>* {{ $t("gears.modalGearTypeLabel") }}:</b></label>
                                <select class="form-control" name="gearTypeAdd" v-model="gearType" required>
                                    <option value="1">{{ $t("gears.modalGearTypeOption1Bike") }}</option>
                                    <option value="2">{{ $t("gears.modalGearTypeOption2Shoes") }}</option>
                                    <option value="3">{{ $t("gears.modalGearTypeOption3Wetsuit") }}</option>
                                </select>
                                <!-- date fields -->
                                <label for="gearDateAdd"><b>* {{ $t("gears.modalDateLabel") }}:</b></label>
                                <input class="form-control" type="date" name="gearDateAdd" :placeholder='$t("gears.modalDatePlaceholder")' v-model="date" required>
                                <p>* {{ $t("generalItens.requiredField") }}</p>
                            </div>
                            <div class="modal-footer">
                                <button type="button" class="btn btn-secondary" data-bs-dismiss="modal">{{ $t("generalItens.buttonClose") }}</button>
                                <button type="submit" class="btn btn-success" name="addGear" data-bs-dismiss="modal">{{ $t("gears.buttonAddGear") }}</button>
                            </div>
                        </form>
                    </div>
                </div>
            </div>

            <!-- Search gear by nickname zone -->
            <br>
            <p class="mt-2">{{ $t("gears.subTitleSearchGearByNickname") }}:</p>
            <form>
                <div class="mb-3">
                    <input class="form-control" type="text" name="gearNickname" :placeholder='$t("gears.placeholderSearchGearByNickname")' v-model="searchNickname" required>
                </div>
            </form>
        </div>
        <div class="col">
            <!-- Error alerts -->
            <ErrorToastComponent v-if="errorMessage" />

            <!-- Success banners -->
            <SuccessToastComponent v-if="successMessage" />

            <div v-if="isLoading">
                <LoadingComponent />
            </div>
            <div v-else>
                <!-- Checking if userGears is loaded and has length -->
                <div v-if="userGears && userGears.length">
                    <!-- Iterating over userGears to display them -->
                    <p>{{ $t("gears.displayUserNumberOfGears1") }}{{ userGearsNumber }}{{ $t("gears.displayUserNumberOfGears2") }}{{ userGears.length }}{{ $t("gears.displayUserNumberOfGears3") }}</p>
                    <ul class="list-group list-group-flush" v-for="gear in userGears" :key="gear.id" :gear="gear">
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
                                    <b>{{ $t("gears.gearTypeLabel") }}</b>
                                    <span v-if="gear.gear_type == 1">{{ $t("gears.gearTypeOption1") }}</span>
                                    <span v-else-if="gear.gear_type == 2">{{ $t("gears.gearTypeOption2") }}</span>
                                    <span v-else>{{ $t("gears.gearTypeOption3") }}</span>
                                    <br>
                                </div>
                            </div>
                            <div>
                                <span class="badge bg-success-subtle border border-success-subtle text-success-emphasis align-middle" v-if="gear.is_active == 1">{{ $t("gears.activeState") }}</span>
                                <span class="badge bg-danger-subtle border border-danger-subtle text-danger-emphasis align-middle" v-else>{{ $t("gears.inactiveState") }}</span>
                                <span class="badge bg-primary-subtle border border-primary-subtle text-primary-emphasis align-middle" v-if="gear.strava_gear_id">{{ $t("gears.gearFromStrava") }}</span>
                            </div>
                        </li>
                    </ul>
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
import { ref, onMounted, onUnmounted, watch } from 'vue';
import { useI18n } from 'vue-i18n';
import { useRoute } from 'vue-router';
// Importing the stores
import { useSuccessAlertStore } from '@/stores/Alerts/successAlert';
import { useErrorAlertStore } from '@/stores/Alerts/errorAlert';
// Importing the components
import NoItemsFoundComponent from '@/components/NoItemsFoundComponents.vue';
import ErrorToastComponent from '@/components/Toasts/ErrorToastComponent.vue';
import SuccessToastComponent from '@/components/Toasts/SuccessToastComponent.vue';
import LoadingComponent from '@/components/LoadingComponent.vue';
import BackButtonComponent from '@/components/BackButtonComponent.vue';
// Importing the services
import { gears } from '@/services/gears';

//import { Modal } from 'bootstrap';

export default {
    components: {
        NoItemsFoundComponent,
        LoadingComponent,
        ErrorToastComponent,
        SuccessToastComponent,
        BackButtonComponent,
    },
    setup() {
        const { t } = useI18n();
        const route = useRoute();
        const errorAlertStore = useErrorAlertStore();
        const successAlertStore = useSuccessAlertStore();
        const brand = ref('');
        const model = ref('');
        const nickname = ref('');
        const gearType = ref(1);
        const date = ref(null);
        const isLoading = ref(true);
        const errorMessage = ref('');
        const successMessage = ref('');
        const userGears = ref([]);
        const userGearsNumber = ref(0);
        const userHasMoreGears = ref(true);
        const pageNumber = ref(1);
        const numRecords = 5;
        const searchNickname = ref('');

        /**
         * Fetches more gears from the server.
         * 
         * @async
         * @function fetchMoreGears
         * @returns {Promise<void>}
         */
        async function fetchMoreGears() {
            // If the component is already loading or there are no more gears to fetch, return.
            if (isLoading.value || !userHasMoreGears.value) return;

            // Add 1 to the page number.
            pageNumber.value++;
            try {
                // Fetch the gears from the server.
                const newGears = await gears.getUserGearsWithPagination(pageNumber.value, numRecords);
                Array.prototype.push.apply(userGears.value, newGears);

                // If there are no more gears to fetch, set userHasMoreGears to false.
                if ((pageNumber.value * numRecords) >= userGearsNumber.value) {
                    userHasMoreGears.value = false;
                }
            } catch (error) {
                // If there is an error, set the error message and show the error alert.
                errorMessage.value = t('generalItens.errorFetchingInfo') + " - " + error.toString();
                errorAlertStore.setAlertMessage(errorMessage.value);
            }
        }

        /**
         * Performs a search for gears based on the provided nickname.
         * If the search nickname is empty, the function will handle it accordingly.
         * If the search is successful, the userGears value will be updated with the results.
         * If an error occurs during the search, an error message will be displayed and an alert will be set.
         */
        async function performSearch() {
            // If the search nickname is empty, reset the list to initial state.
            if (!searchNickname.value) {
                // Reset the list to the initial state when search text is cleared
                pageNumber.value = 1;
                userHasMoreGears.value = true;

                await fetchInitialGears();

                return;
            }
            try {
                // Fetch the gears based on the search nickname.
                const results = await gears.getGearByNickname(searchNickname.value);
                // Update the userGears value with the search results.
                userGears.value = results;
            } catch (error) {
                // If there is an error, set the error message and show the error alert.
                errorMessage.value = t('generalItens.errorFetchingInfo') + " - " + error.toString();
                errorAlertStore.setAlertMessage(errorMessage.value);
            }
        }

        /**
         * Handles the scroll event and triggers the fetchMoreGears function when the user reaches the bottom of the window.
         */
        function handleScroll() {
            // If the user has reached the bottom of the window, fetch more gears.
            const bottomOfWindow = document.documentElement.scrollTop + window.innerHeight === document.documentElement.offsetHeight;

            if (bottomOfWindow) {
                fetchMoreGears();
            }
        }

        /**
         * Submits the form to add a new gear.
         * 
         * @async
         * @function submitAddGearForm
         * @throws {Error} If there is an error while creating the gear.
         * @returns {Promise<void>} A promise that resolves when the gear is successfully added.
         */
        async function submitAddGearForm() {
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

                // Set the success message and show the success alert.
                successMessage.value = t('gears.successGearAdded');
                successAlertStore.setAlertMessage(successMessage.value);
                successAlertStore.setClosableState(true);
            } catch (error) {
                // If there is an error, set the error message and show the error alert.
                errorMessage.value = t('generalItens.errorFetchingInfo') + " - " + error.toString();
                errorAlertStore.setAlertMessage(errorMessage.value);
            }
        }

        /**
         * Fetches the initial gears for the user.
         * 
         * @async
         * @function fetchInitialGears
         * @throws {Error} If there is an error while creating the gear.
         * @returns {Promise<void>} A promise that resolves when the initial gears are fetched.
         */
        async function fetchInitialGears() {
            try {
                // Fetch the user gears with pagination.
                userGears.value = await gears.getUserGearsWithPagination(pageNumber.value, numRecords);
                // Get the total number of user gears.
                userGearsNumber.value = await gears.getUserGearsNumber();

                // If there are no more gears to fetch, set userHasMoreGears to false.
                if ((pageNumber.value * numRecords) >= userGearsNumber.value) {
                    userHasMoreGears.value = false;
                }
            } catch (error) {
                // If there is an error, set the error message and show the error alert.
                errorMessage.value = t('generalItens.errorFetchingInfo') + " - " + error.toString();
                errorAlertStore.setAlertMessage(errorMessage.value);
            }
        }

        /**
         * Initializes the component and fetches user gears with pagination.
         * Attaches a scroll event listener to the window.
         * 
         * @returns {void}
         */
        onMounted(async () => {
            if (route.query.gearDeleted === 'true') {
                // Set the gearDeleted value to true and show the success alert.
                successMessage.value = t("gears.successGearDeleted");
                successAlertStore.setAlertMessage(successMessage.value);
                successAlertStore.setClosableState(true);
            }

            if (route.query.gearFound === 'false') {
                // Set the gearFound value to false and show the error alert.
                errorMessage.value = t('gears.errorGearNotFound');
                errorAlertStore.setAlertMessage(errorMessage.value);
                errorAlertStore.setClosableState(true);
            }

            // Add the event listener for scroll event.
            window.addEventListener('scroll', handleScroll);

            await fetchInitialGears();

            isLoading.value = false;
        });

        /**
         * Removes the event listener for scroll when the component is unmounted.
         * @function onUnmounted
         * @param {Function} handleScroll - The event handler function for scroll event.
         */
        onUnmounted(() => {
            // Remove the event listener for scroll event.
            window.removeEventListener('scroll', handleScroll);
        });

        /**
         * Watches the `searchNickname` property and performs a search when it changes.
         * @param {string} searchNickname - The nickname to search for.
         * @param {Function} performSearch - The function to perform the search.
         * @param {Object} options - The options for the watcher.
         * @param {boolean} options.immediate - Whether to immediately invoke the watcher callback.
         */
        watch(searchNickname, performSearch, { immediate: false });

        return {
            brand,
            model,
            nickname,
            gearType,
            date,
            isLoading,
            errorMessage,
            successMessage,
            userGears,
            userGearsNumber,
            searchNickname,
            t,
            submitAddGearForm,
        };
    },
};
</script>