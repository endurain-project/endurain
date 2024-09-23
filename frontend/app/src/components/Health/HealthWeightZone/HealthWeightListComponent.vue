<template>
    <li class="list-group-item d-flex justify-content-between">
        <div class="d-flex align-items-center">
            <font-awesome-icon :icon="['fas', 'weight']"     size="2x" />
            <div class="ms-3">
                <div class="fw-bold">
                    {{ data.weight }}
                </div>
                {{ formatDate(data.created_at) }}
            </div>
        </div>
        <div>
            <!-- edit weight button -->
            <a class="btn btn-link btn-lg link-body-emphasis" href="#" role="button" data-bs-toggle="modal" :data-bs-target="`#editWeightId${data.id}`"><font-awesome-icon :icon="['fas', 'fa-pen-to-square']" /></a>

            <HealthWeightAddEditModalComponent :action="'edit'" :data="data" @editedWeight="updateWeightListEdited" />
        </div>
    </li>
</template>

<script>
import HealthWeightAddEditModalComponent from './HealthWeightAddEditModalComponent.vue';

export default {
	components: {
        HealthWeightAddEditModalComponent,
	},
	props: {
		data: {
			type: Object,
			required: true,
		},
	},
    emits: ["editedWeight"],
	setup(props) {
        const formatDate = (dateString) => {
            const date = new Date(dateString);
            return `${date.getDate().toString().padStart(2, '0')}-${(date.getMonth() + 1).toString().padStart(2, '0')}-${date.getFullYear()}`;
        };

        function updateWeightListEdited(editedWeight){
            emit("editedWeight", editedWeight);
        }

		return {
            formatDate,
            updateWeightListEdited,
		};
	},
};
</script>