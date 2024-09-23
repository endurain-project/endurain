<template>
    <div class="col">
        <LoadingComponent v-if="isLoading" />
        <div v-else>
            <!-- add weight button -->
            <a class="w-100 btn btn-primary" href="#" role="button" data-bs-toggle="modal" data-bs-target="#addWeightModal">{{ $t("healthWeightZoneComponent.buttonAddWeight") }}</a>

            <HealthWeightAddEditModalComponent :action="'add'" @isLoadingNewWeight="updateIsLoadingNewWeight" @createdWeight="updateWeightListAdded" />
            
            <!-- Checking if dataWithWeight is loaded and has length -->
            <div v-if="dataWithWeight && dataWithWeight.length" class="mt-3">
                <!-- show graph -->
                <HealthWeightLineChartComponent :userHealthData="dataWithWeight" :isLoading="isLoading" />

                <!-- Displaying loading new gear if applicable -->
                <ul class="mt-3 list-group list-group-flush" v-if="isLoadingNewWeight">
                        <li class="list-group-item rounded">
                            <LoadingComponent />
                        </li>
                    </ul>

                <!-- list zone -->
                <ul class="mt-3 list-group list-group-flush"  v-for="data in dataWithWeight" :key="data.id" :data="data">
                    <HealthWeightListComponent :data="data" />
                </ul>

                <!-- pagination area -->
                <PaginationComponent :totalPages="totalPages" :pageNumber="pageNumber" />
            </div>
            <!-- Displaying a message or component when there are no weight measurements -->
            <div v-else class="mt-3">
                <br>
                <NoItemsFoundComponent />
            </div>
        </div>
    </div>
</template>

<script>
import { ref } from "vue";
import HealthWeightAddEditModalComponent from './HealthWeightZone/HealthWeightAddEditModalComponent.vue';
import HealthWeightLineChartComponent from './HealthWeightZone/HealthWeightLineChartComponent.vue';
import HealthWeightListComponent from './HealthWeightZone/HealthWeightListComponent.vue';
import LoadingComponent from '../GeneralComponents/LoadingComponent.vue';
import NoItemsFoundComponent from '../GeneralComponents/NoItemsFoundComponents.vue';
import PaginationComponent from '../GeneralComponents/PaginationComponent.vue';

export default {
	components: {
        HealthWeightAddEditModalComponent,
        HealthWeightLineChartComponent,
        HealthWeightListComponent,
        LoadingComponent,
        NoItemsFoundComponent,
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
    emits: ["createdWeight"],
	setup(props, { emit }) {
        const dataWithWeight = [];
        for(let data of props.userHealthData){
            if(data.weight){
                dataWithWeight.push(data)
            }
        }
        const isLoadingNewWeight = ref(false);

        function updateIsLoadingNewWeight(isLoadingNewWeightNewValue) {
            isLoadingNewWeight.value = isLoadingNewWeightNewValue;
        }

        function updateWeightListAdded(createdWeight) {
			emit("createdWeight", createdWeight);
		}

		return {
            dataWithWeight,
            isLoadingNewWeight,
            updateIsLoadingNewWeight,
            updateWeightListAdded,
		};
	},
};
</script>