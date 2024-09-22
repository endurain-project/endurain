<template>
    <div class="col">
        <div class="card mb-3">
            <div class="card-body">
                Current weight is {{ userHealthData.weight }} and target is {{ userHealthTargets.weight }}
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
            type: Object,
            required: true,
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