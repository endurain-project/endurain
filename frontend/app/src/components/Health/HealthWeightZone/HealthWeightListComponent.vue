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
    </li>
</template>

<script>

export default {
	components: {

	},
	props: {
		data: {
			type: Object,
			required: true,
		},
	},
	setup(props) {
        const formatDate = (dateString) => {
            const date = new Date(dateString);
            return `${date.getDate().toString().padStart(2, '0')}-${(date.getMonth() + 1).toString().padStart(2, '0')}-${date.getFullYear()}`;
        };

		return {
            formatDate,
		};
	},
};
</script>