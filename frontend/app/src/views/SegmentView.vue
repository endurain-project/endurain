<template>
	<div class="bg-body-tertiary rounded p-3 shadow-sm">
		<LoadingComponent v-if="isLoading" />

        <div v-else>
            <SegmentSummaryComponent :segment="segment" :activitySegments="activitySegments" :source="'segment'" />
        </div>
        <!-- details component Zone -->
        <div class="mt-3 mb-3" v-if="isLoading">
            <LoadingComponent />
        </div>
        <div v-else>
            <SegmentDetailComponent :activity-segments="activitySegments" :segment="segment" />
        </div>
    </div>
</template>

<script setup>
import { ref, onMounted } from 'vue';
import { useI18n } from "vue-i18n";
import { useRoute, useRouter } from 'vue-router';

import { useAuthStore } from "@/stores/authStore";
import { segments } from '@/services/segmentsService';

import { push } from "notivue";
// Importing the components
import SegmentSummaryComponent from "@/components/Activities/SegmentSummaryComponent.vue";
import SegmentDetailComponent from '@/components/Activities/SegmentDetailComponent.vue';

import LoadingComponent from "@/components/GeneralComponents/LoadingComponent.vue";

import { activitySegments as actSegments } from '@/services/activitySegmentsService';

const { t } = useI18n();
const authStore = useAuthStore();
const route = useRoute();
const router = useRouter();
const isLoading = ref(true);
const segment = ref(null);
const activitySegments = ref(null);

onMounted(async () => {
    try {
        // Get the segment by id
        if (authStore.isAuthenticated) {
            segment.value = await segments.getSegmentById(route.params.id);
            activitySegments.value = await segments.getActivitySegments(route.params.id)
        }

        // Check if the segment exists
        if (!segment.value) {
            return router.push({
                path: "/segments",
                query: { segmentFound: "false", id: route.params.id },
            });
        }

        // Check if the segment is owned by the current user
        if (segment.value.user_id != authStore.user.id) {
            return router.push({
                path: "/segments",
                query: { segmentFound: "false", id: route.params.id },
            });
        }

	} catch (error) {
		if (error.toString().includes("422")) {
			router.push({
				path: "/",
				query: { segmentFound: "false", id: route.params.id },
			});
		}
		// If there is an error, set the error message and show the error alert.
		push.error(
			`${t("segmentView.errorMessageSegmentNotFound")} - ${error}`,
		);
	}

	isLoading.value = false;
    
	//if (authStore.user.id === segment.value.user_id) {
	//}
})

</script>