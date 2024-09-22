<template>
    <div class="col">
        <HealthWeightLineChartComponent :userHealthData="userHealthData" :isLoading="isLoading" />

        <LoadingComponent v-if="isLoading" />
        <div v-else>
            <!-- Checking if usersArray is loaded and has length -->
            <div v-if="userHealthData && userHealthData.length">
                <!-- list zone -->
                <ul class="list-group list-group-flush"  v-for="data in userHealthData" :key="data.id" :data="data">
                    <HealthWeightListComponent :data="data" />
                </ul>

                <!-- pagination area -->
                <PaginationComponent :totalPages="totalPages" :pageNumber="pageNumber" />
            </div>
            <!-- Displaying a message or component when there are no activities -->
            <div v-else>
                <br>
                <NoItemsFoundComponent />
            </div>
        </div>
    </div>
</template>

<script>
import HealthWeightLineChartComponent from './HealthWeightZone/HealthWeightLineChartComponent.vue';
import HealthWeightListComponent from './HealthWeightZone/HealthWeightListComponent.vue';
import LoadingComponent from '../GeneralComponents/LoadingComponent.vue';
import NoItemsFoundComponents from '../GeneralComponents/NoItemsFoundComponents.vue';
import PaginationComponent from '../GeneralComponents/PaginationComponent.vue';

export default {
	components: {
        HealthWeightLineChartComponent,
        HealthWeightListComponent,
        LoadingComponent,
        NoItemsFoundComponents,
        PaginationComponent,
	},
    props: {
        userHealthData: {
            type: Object,
            required: true,
        },
        userHealthTargets: {
            type: Object,
            required: true,
        },
        isLoading: {
            type: Boolean,
            required: true,
        },
        totalPages: {
            type: Number,
            required: true,
        },
        pageNumber: {
            type: Number,
            required: true,
        },
    },
	setup(props) {
		

		return {

		};
	},
};
</script>