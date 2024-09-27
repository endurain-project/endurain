<template>
    <div class="col">
        <div class="card mb-3">
            <div class="card-body">
                <span v-if="userHealthData">Current weight is {{ userHealthData.weight }} and target is {{ userHealthTargets.weight }}</span>
                <span v-else>No weight data for user</span>
            </div>
        </div>
    </div>
</template>

<script>

export default {
	components: {
        
	},
    props: {
        userHealthData: {
            type: [Object, null],
            required: true,
            default: null,
        },
        userHealthTargets: {
            type: Object,
            required: true,
        },
    },
	setup(props) {
		return {

		};
	},
};
</script>