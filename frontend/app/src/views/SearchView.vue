<template>
    <div class="mx-auto " style="max-width: 650px;">
        <h1>{{ $t("searchView.searchSelectLabel") }}</h1>
        <form class="bg-body-tertiary rounded p-3 shadow-sm">
            <div class="input-group">
                <!-- Select type -->
                <select id="inputSelectTypeToSearch" class="form-select rounded me-1" v-model="searchSelectValue">
                    <option value="1">{{ $t("searchView.searchSelectOptionUser") }}</option>
                    <option value="2">{{ $t("searchView.searchSelectOptionActivity") }}</option>
                    <option value="3">{{ $t("searchView.searchSelectOptionGear") }}</option>
                </select>
                <!-- Activity type area -->
                <select id="inputSelectActivityTypeToSearch" class="form-select rounded me-1" v-model="searchSelectActivityType" v-if="searchSelectValue == 2">
                    <option value="0">{{ $t("searchView.searchSelectActivityType0") }}</option>
                    <option value="1">{{ $t("searchView.searchSelectActivityType1") }}</option>
                    <option value="2">{{ $t("searchView.searchSelectActivityType2") }}</option>
                    <option value="3">{{ $t("searchView.searchSelectActivityType3") }}</option>
                    <option value="4">{{ $t("searchView.searchSelectActivityType4") }}</option>
                    <option value="5">{{ $t("searchView.searchSelectActivityType5") }}</option>
                    <option value="6">{{ $t("searchView.searchSelectActivityType6") }}</option>
                    <option value="7">{{ $t("searchView.searchSelectActivityType7") }}</option>
                    <option value="8">{{ $t("searchView.searchSelectActivityType8") }}</option>
                    <option value="9">{{ $t("searchView.searchSelectActivityType9") }}</option>
                    <option value="10">{{ $t("searchView.searchSelectActivityType10") }}</option>
                    <option value="11">{{ $t("searchView.searchSelectActivityType11") }}</option>
                </select>
                <!-- Gear type area -->
                <select id="inputSelectGearTypeToSearch" class="form-select rounded me-1" v-model="searchSelectGearType" v-if="searchSelectValue == 3">
                    <option value="0">{{ $t("searchView.searchSelectGearType0") }}</option>
                    <option value="1">{{ $t("searchView.searchSelectGearType1") }}</option>
                    <option value="2">{{ $t("searchView.searchSelectGearType2") }}</option>
                    <option value="3">{{ $t("searchView.searchSelectGearType3") }}</option>
                </select>
                <!-- Search area -->
                <input type="text" class="form-control rounded" id="inputTextFieldToSearch" :placeholder='$t("searchView.searchInputPlaceholder")' v-model="inputSearch">
            </div>
        </form>
        <div v-if="isLoading" class="pt-2">
            <LoadingComponent />
        </div>
        <div v-else>
            <ul v-if="searchResults && searchResults.length" class="list-group list-group-flush mt-1 rounded">
                <li v-for="result in searchResults" :key="result.id" class="list-group-item d-flex justify-content-between bg-body-tertiary">
                    <div class="d-flex align-items-center">
                        <!-- icon for user -->
                        <font-awesome-icon :icon="['fas', 'user']" v-if="searchSelectValue == 1" />
                        <!-- icons for activities -->
                        <font-awesome-icon :icon="['fas', 'person-running']" v-if="searchSelectValue == 2 && [1, 2, 3].includes(Number(result.activity_type))" class="ms-1" />
                        <font-awesome-icon :icon="['fas', 'person-biking']" v-if="searchSelectValue == 2 && [4, 5, 6, 7].includes(Number(result.activity_type))" />
                        <font-awesome-icon :icon="['fas', 'person-swimming']" v-if="searchSelectValue == 2 && [8, 9].includes(Number(result.activity_type))" />
                        <font-awesome-icon :icon="['fas', 'dumbbell']" v-if="searchSelectValue == 2 && [10, 19, 20].includes(Number(result.activity_type))" />
                        <font-awesome-icon :icon="['fas', 'person-walking']" v-if="searchSelectValue == 2 && [11].includes(Number(result.activity_type))" class="ms-1 me-1" />
                        <font-awesome-icon :icon="['fas', 'person-hiking']" v-if="searchSelectValue == 2 && [12].includes(Number(result.activity_type))" />
                        <font-awesome-icon :icon="['fas', 'person-sailboat']" v-if="searchSelectValue == 2 && [13].includes(Number(result.activity_type))" />
                        <font-awesome-icon :icon="['fas', 'hands-praying']" v-if="searchSelectValue == 2 && [14].includes(Number(result.activity_type))" />
                        <font-awesome-icon :icon="['fas', 'person-person-skiing']" v-if="searchSelectValue == 2 && [15].includes(Number(result.activity_type))" />
                        <font-awesome-icon :icon="['fas', 'person-hands-snowboarding']" v-if="searchSelectValue == 2 && [16].includes(Number(result.activity_type))" />
                        <font-awesome-icon :icon="['fas', 'table-tennis-paddle-ball']" v-if="searchSelectValue == 2 && [21, 22, 23, 24, 25, 26].includes(Number(result.activity_type))" />
                        <!-- icons for gears -->
                        <font-awesome-icon :icon="['fas', 'bicycle']" v-if="searchSelectValue == 3 && [1].includes(Number(result.gear_type))" />
                        <font-awesome-icon :icon="['fas', 'person-running']" v-if="searchSelectValue == 3 && [2].includes(Number(result.gear_type))" class="ms-1"/>
                        <font-awesome-icon :icon="['fas', 'swimmer']" v-if="searchSelectValue == 3 && [3].includes(Number(result.gear_type))" />
                        <font-awesome-icon :icon="['fas', 'table-tennis-paddle-ball']" v-if="searchSelectValue == 3 && [4].includes(Number(result.gear_type))" />
                        <div class="ms-3">
                            <div class="fw-bold">
                                <router-link :to="{ name: 'user', params: { id: result.id }}" class="link-body-emphasis link-underline-opacity-0 link-underline-opacity-100-hover" v-if="searchSelectValue == 1" @click="closeSearch">
                                    {{ result.name}}
                                </router-link>
                                <router-link :to="{ name: 'activity', params: { id: result.id }}" class="link-body-emphasis link-underline-opacity-0 link-underline-opacity-100-hover" v-if="searchSelectValue == 2" @click="closeSearch">
                                    {{ result.name}}
                                </router-link>
                                <router-link :to="{ name: 'gear', params: { id: result.id }}" class="link-body-emphasis link-underline-opacity-0 link-underline-opacity-100-hover" v-if="searchSelectValue == 3" @click="closeSearch">
                                    {{ result.nickname }}
                                </router-link>
                            </div>
                            <span v-if="searchSelectValue == 1">{{ result.username }}</span>
                            <span v-else-if="searchSelectValue == 2">{{ formatDateMed(result.start_time) }}</span>
                            <span v-else="searchSelectValue == 3">{{ formatDateMed(result.created_at) }}</span>
                        </div>
                    </div>
                    <div>
                        <span class="badge bg-danger-subtle border border-danger-subtle text-danger-emphasis align-middle" v-if="result.is_active == 0">{{ $t("searchView.resultIsInactiveBadge") }}</span>
                    </div>
                </li>
            </ul>
            <div v-else>
                <NoItemsFoundComponents class="mt-1" v-if="inputSearch"/>
            </div>
        </div>
    </div>
</template>

<script>
import { watch, ref } from "vue";
import { useI18n } from "vue-i18n";
// Import Notivue push
import { push } from "notivue";
// import lodash
import { debounce } from "lodash";
import { useAuthStore } from "@/stores/authStore";
import { users } from "@/services/usersService";
import { gears } from "@/services/gearsService";
import { activities } from "@/services/activitiesService";
import { formatDateMed } from "@/utils/dateTimeUtils";
// import components
import LoadingComponent from "@/components/GeneralComponents/LoadingComponent.vue";
import NoItemsFoundComponents from "@/components/GeneralComponents/NoItemsFoundComponents.vue";

export default {
    components: {
        LoadingComponent,
        NoItemsFoundComponents,
    },
	emits: ["collapseNavbar", "toggleShowSearch"],
	setup(props, { emit }) {
		const authStore = useAuthStore();
		const { t } = useI18n();
        const isLoading = ref(false);
		const searchSelectValue = ref("1");
		const searchSelectActivityType = ref("0");
        const searchSelectGearType = ref("0");
		const inputSearch = ref("");
		const searchResultsOriginal = ref([]);
		const searchResults = ref([]);

		const fetchUserResults = debounce(async (query) => {
			if (!query) {
                isLoading.value = false;
				searchResultsOriginal.value = [];
				searchResults.value = [];
				return;
			}
			try {
				searchResultsOriginal.value =
					await users.getUserContainsUsername(query);
				searchResults.value = searchResultsOriginal.value;
			} catch (error) {
				push.error(
					`${t("navbarSearchComponent.errorFetchingUserWithUsernameContains")} - ${error}`,
				);
			}
            isLoading.value = false;
		}, 500);

		const fetchActivityResults = debounce(async (query) => {
			if (!query) {
                isLoading.value = false;
				searchResultsOriginal.value = [];
				searchResults.value = [];
				return;
			}
			try {
				searchResultsOriginal.value = await activities.getActivityByName(query);
				updateSearchResultsBasedOnActivityType();
			} catch (error) {
				push.error(
					`${t("navbarSearchComponent.errorFetchingActivityWithNameContains")} - ${error}`,
				);
			}
            isLoading.value = false;
		}, 500);

		const fetchGearResults = debounce(async (query) => {
			if (!query) {
                isLoading.value = false;
				searchResultsOriginal.value = [];
				searchResults.value = [];
				return;
			}
			try {
				searchResultsOriginal.value =
					await gears.getGearContainsNickname(query);
                    updateSearchResultsBasedOnGearType();
			} catch (error) {
				push.error(
					`${t("navbarSearchComponent.errorFetchingGearWithNicknameContains")} - ${error}`,
				);
			}
            isLoading.value = false;
		}, 500);

        function updateSearchResultsBasedOnActivityType() {
            if (searchSelectActivityType.value === "1") {
                searchResults.value = searchResultsOriginal.value.filter((user) =>
                    [1, 2, 3].includes(user.activity_type),
                );
            } else if (searchSelectActivityType.value === "2") {
                searchResults.value = searchResultsOriginal.value.filter((user) =>
                    [4, 5, 6, 7, 27].includes(user.activity_type),
                );
            } else if (searchSelectActivityType.value === "3") {
                searchResults.value = searchResultsOriginal.value.filter((user) =>
                    [8, 9].includes(user.activity_type),
                );
            } else if (searchSelectActivityType.value === "4") {
                searchResults.value = searchResultsOriginal.value.filter((user) =>
                    [10, 19, 20].includes(user.activity_type),
                );
            } else if (searchSelectActivityType.value === "5") {
                searchResults.value = searchResultsOriginal.value.filter((user) =>
                    [11].includes(user.activity_type),
                );
            } else if (searchSelectActivityType.value === "6") {
                searchResults.value = searchResultsOriginal.value.filter((user) =>
                    [12].includes(user.activity_type),
                );
            } else if (searchSelectActivityType.value === "7") {
                searchResults.value = searchResultsOriginal.value.filter((user) =>
                    [13].includes(user.activity_type),
                );
            } else if (searchSelectActivityType.value === "8") {
                searchResults.value = searchResultsOriginal.value.filter((user) =>
                    [14].includes(user.activity_type),
                );
            } else if (searchSelectActivityType.value === "9") {
                searchResults.value = searchResultsOriginal.value.filter((user) =>
                    [15].includes(user.activity_type),
                );
            } else if (searchSelectActivityType.value === "10") {
                searchResults.value = searchResultsOriginal.value.filter((user) =>
                    [16].includes(user.activity_type),
                );
            } else if (searchSelectActivityType.value === "11") {
                searchResults.value = searchResultsOriginal.value.filter((user) =>
                    [21, 22, 23, 24, 25, 26].includes(user.activity_type),
                );
            } else {
                searchResults.value = searchResultsOriginal.value;
            }
        };

        function updateSearchResultsBasedOnGearType() {
            if (searchSelectGearType.value === "1") {
                searchResults.value = searchResultsOriginal.value.filter((user) =>
                    [1].includes(user.gear_type),
                );
            } else if (searchSelectGearType.value === "2") {
                searchResults.value = searchResultsOriginal.value.filter((user) =>
                    [2].includes(user.gear_type),
                );
            } else if (searchSelectGearType.value === "3") {
                searchResults.value = searchResultsOriginal.value.filter((user) =>
                    [3].includes(user.gear_type),
                );
            } else {
                searchResults.value = searchResultsOriginal.value;
            }
        }

		// Watchers
		watch(searchSelectValue, () => {
            isLoading.value = false;
			inputSearch.value = "";
			searchResultsOriginal.value = [];
			searchResults.value = [];
		});

		watch(searchSelectActivityType, () => {
            updateSearchResultsBasedOnActivityType();
		});

        watch(searchSelectGearType, () => {
            updateSearchResultsBasedOnGearType();
        });

		watch(inputSearch, async (newQuery) => {
            isLoading.value = true;
			if (searchSelectValue.value === "1") {
				await fetchUserResults(newQuery);
			} else if (searchSelectValue.value === "2") {
				await fetchActivityResults(newQuery);
			} else if (searchSelectValue.value === "3") {
				await fetchGearResults(newQuery);
			}
		});

		const closeSearch = () => {
			emit("toggleShowSearch");
			emit("collapseNavbar");
		};

		return {
			t,
			authStore,
            isLoading,
			searchSelectValue,
			searchSelectActivityType,
            searchSelectGearType,
			inputSearch,
			searchResultsOriginal,
			searchResults,
			closeSearch,
			formatDateMed,
		};
	},
};
</script>