<template>
	<Suspense>
		<template #default>
			<slot />
		</template>
		<template #fallback>
			<LoadingComponent />
		</template>
	</Suspense>
</template>

<script>
import LoadingComponent from './LoadingComponent.vue';

export default {
	name: 'SuspenseWrapper',
	components: {
		LoadingComponent,
	},
};
</script>
