<template>
    <td>
        <font-awesome-icon :icon="getIcon(segment.activity_type)"/>
    </td>
    <td>
        <router-link :to="{ name: 'segment', params: { id: segment.id } }" class="link-body-emphasis link-underline-opacity-0 link-underline-opacity-100-hover">
            {{ segment.name }}
        </router-link>
    </td>
    <td>{{ formatSegmentLocation(segment) }}</td>
    <td class="d-none d-md-table-cell">{{ segment.num_activities }}</td>
    <td class="d-none d-md-table-cell">{{ formatDateTime(segment.most_recent_activity) }}</td>
</template>

<script setup>
// Importing the utils
import {
	formatDateTime,
	getIcon,
} from "@/utils/activityUtils";
import {formatSegmentLocation} from "@/utils/segmentUtils";

// Define props
const props = defineProps({
    segment: {
        type: Object,
        required: true,
    }
});

</script>