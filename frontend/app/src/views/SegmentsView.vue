<template>
<h1>{{ $t('segmentsView.title') }}</h1>
<!-- Filter Section -->
	<div class="p-3 mb-3 bg-body-tertiary border-0 rounded">
		<div class="row align-items-end">
			<!-- Activity Type -->
			<div class="col-md-3">
				<label for="activityTypeFilter" class="form-label">{{ $t('segmentsView.filterLabelType') }}</label>
				<select id="activityTypeFilter" class="form-select" v-model="selectedType" @change="applyFilters">
					<option value="">{{ $t('segmentsView.filterOptionAllTypes') }}</option>
					<option v-for="(value, key) in activityTypes" :key="key" :value="key">{{ value }}</option>
				</select>
			</div>
			<!-- Name Search -->
			<div class="col-md-3">
				<label for="nameSearchFilter" class="form-label">{{ $t('segmentsView.filterLabelNameLocation')
				}}</label>
				<input type="text" id="nameSearchFilter" class="form-control" v-model="nameSearch"
					:placeholder="$t('segmentsView.filterPlaceholderNameLocation')" />
			</div>
			<!-- Buttons -->
			<div class="col-12 mt-3 d-flex justify-content-end gap-3">
				<button type="button" class="btn btn-secondary" @click="clearFilters">{{
					$t('segmentsView.buttonClear') }}</button>
				<button type="submit" class="btn btn-primary" disabled v-if="isLoading">
					<span class="spinner-border spinner-border-sm me-1" aria-hidden="true"></span>
					<span role="status">{{ $t('segmentsView.buttonApply') }}</span>
				</button>
				<button type="submit" class="btn btn-primary" @click="applyFilters" v-else>{{ $t('segmentsView.buttonApply') }}</button>
			</div>
		</div>
	</div>
<!-- End Filter Section -->

	<LoadingComponent v-if="isLoading" />
	<div class="p-3 bg-body-tertiary rounded shadow-sm" v-else-if="segments && segments.length">
		<!-- Segments Table -->
		<SegmentsTableComponent :segments="segments" :sort-by="sortBy" :sort-order="sortOrder"
			@sortChanged="handleSort" v-if="segments && segments.length" />

		<PaginationComponent :totalPages="totalPages" :pageNumber="pageNumber" @pageNumberChanged="setPageNumber"
			v-if="segments && segments.length" />
	</div>

	<NoItemsFoundComponents v-else />
</template>


<script setup>
import { ref, onMounted, watch } from "vue";
import { useI18n } from "vue-i18n";
import { debounce } from "lodash";
import { push } from "notivue";
import { useAuthStore } from "@/stores/authStore";
import { useServerSettingsStore } from "@/stores/serverSettingsStore";
import { segments as segmentsService } from '@/services/segmentsService';
import SegmentsTableComponent from "@/components/Segments/SegmentsTableComponent.vue";
import PaginationComponent from "@/components/GeneralComponents/PaginationComponent.vue";
import LoadingComponent from "@/components/GeneralComponents/LoadingComponent.vue";
import NoItemsFoundComponents from "@/components/GeneralComponents/NoItemsFoundComponents.vue";

const { t } = useI18n();
const authStore = useAuthStore();
const segments = ref([]);
const userNumberSegments = ref(0);
const activityTypes = ref([]);
const pageNumber = ref(1);
const numRecords = useServerSettingsStore().serverSettings.num_records_per_page || 25;
const totalPages = ref(1);
const isLoading = ref(true);

// Filter state
const selectedType = ref("");
const nameSearch = ref("");

// Sorting state
const sortBy = ref("most_recent_activity"); // Default sort column
const sortOrder = ref("desc"); // Default sort order

const performNameSearch = debounce(async () => {
    if (!nameSearch.value) {
        pageNumber.value = 1;
        await applyFilters();
        return;
    }
    try {
        await applyFilters();
    } catch (error) {
        push.error(`${t("segmentsView.errorUpdatingSegments")} - ${error}`);
    }
}, 500);


async function fetchActivityTypes() {
    try {
        activityTypes.value = await segmentsService.getActivityTypes();
    } catch (error) {
        push.error(`${t("segmentsView.errorFailedFetchActivityTypes")} - ${error}`);
    }
}

function setPageNumber(page) {
    pageNumber.value = page;
}

async function updateSegments() {
    try {
        isLoading.value = true;
        await fetchSegments();
    } catch (error) {
        push.error(`${t("segmentsView.errorUpdatingSegments")} - ${error}`);
    } finally {
        isLoading.value = false;
    }
}

async function fetchSegments() {
    segments.value = [];
    const filters = {
        type: selectedType.value,
        name_search: nameSearch.value,
    };
    try {
        segments.value = await segmentsService.getSegmentsWithPagination(
            authStore.user.id,
            pageNumber.value,
            numRecords,
            filters,
            sortBy.value,
            sortOrder.value
        );

        userNumberSegments.value = await segmentsService.getUserNumberOfSegments(authStore.user.id, filters);
        totalPages.value = Math.ceil(userNumberSegments.value / numRecords);
    } catch (error) {
        push.error(`${t("segmentsView.errorFetchingSegments")} - ${error}`);
    }
}

onMounted(async () => {
    await fetchActivityTypes();
    await updateSegments();
});

async function applyFilters() {
    pageNumber.value = 1; // Reset to first page on filter change
    await updateSegments();
}

async function clearFilters() {
    selectedType.value = "";
    nameSearch.value = "";
    sortBy.value = "most_recent_activity"; // Reset to default sort column
    sortOrder.value = "desc"; // Reset to default sort order
    await updateSegments();
}

async function handleSort(columnName) {
    if (sortBy.value === columnName) {
        sortOrder.value = sortOrder.value === "asc" ? "desc" : "asc"; // Toggle sort order
    } else {
        sortBy.value = columnName; // Set new sort column
        sortOrder.value = "desc"; // Default to descending order
    }
    await updateSegments();
}   

</script>