<template>
	<div class="table-responsive mb-3">
		<table class="table table-borderless table-striped table-hover table-sm rounded" style="--bs-table-bg: var(--bs-gray-850);">
			<thead>
				<tr>
					<th style="cursor: pointer; white-space: nowrap;" @click="changeSort('type')">
						<span class="d-flex align-items-center flex-nowrap">
							{{ $t('segmentsTableComponent.headerType') }} 
							<font-awesome-icon :icon="sortIcon('type')" class="ms-1 opacity-75" />
						</span>
					</th>
					<th style="cursor: pointer; white-space: nowrap;" @click="changeSort('name')">
						<span class="d-flex align-items-center flex-nowrap">
							{{ $t('segmentsTableComponent.headerName') }}
							<font-awesome-icon :icon="sortIcon('name')" class="ms-1 opacity-75" />
						</span>
					</th>
					<th style="cursor: pointer; white-space: nowrap;" @click="changeSort('location')">
						<span class="d-flex align-items-center flex-nowrap">
							{{ $t('segmentsTableComponent.headerLocation') }}
							<font-awesome-icon :icon="sortIcon('location')" class="ms-1 opacity-75" />
						</span>
					</th>
					<th class="d-none d-md-table-cell" style="cursor: pointer; white-space: nowrap;" @click="changeSort('num_activities')">
						<span class="d-flex align-items-center flex-nowrap">
							{{ $t('segmentsTableComponent.headerNumActivities') }}
							<font-awesome-icon :icon="sortIcon('num_activities')" class="ms-1 opacity-75" />
						</span>
					</th>
					<th class="d-none d-md-table-cell" style="cursor: pointer; white-space: nowrap;" @click="changeSort('most_recent_activity')">
						<span class="d-flex align-items-center flex-nowrap">
							{{ $t('segmentsTableComponent.headerLastActivity') }}
							<font-awesome-icon :icon="sortIcon('most_recent_activity')" class="ms-1 opacity-75" />
						</span>
					</th>
				</tr>
      		</thead>
			<tbody>
				<tr v-for="segment in segments" :key="segment.id">
					<SegmentsTableRowComponent :segment="segment" />
				</tr>
      		</tbody>
    	</table>
  	</div>
</template>

<script>
import { useI18n } from "vue-i18n";
// Importing the components
import SegmentsTableRowComponent from "@/components/Segments/SegmentsTableRowComponent.vue";

export default {
    components: {
        SegmentsTableRowComponent,
    },
    props: {
        segments: {
            type: Array,
            required: true,
            default: () => [],
        },
        sortBy: {
            type: String,
            default: "most_recent_activity",
        },
        sortOrder: {
            type: String,
            default: "desc",
        },
    },
    emits: ["sortChanged"],
    setup(props, { emit }) {
        const { t } = useI18n();

        function changeSort(columnName) {
            emit("sortChanged", columnName);
        }

        function sortIcon(columnName) {
            if (props.sortBy !== columnName) {
                return ["fas", "sort"]; // Default sort icon
            }
            if (props.sortOrder === "asc") {
                return ["fas", "sort-up"]; // Ascending icon
            }
            return ["fas", "sort-down"]; // Descending icon
        }

        return {
            t,
            changeSort,
            sortIcon,
        };
    },
};

</script>