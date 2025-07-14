<template>
    <ul class="list-group list-group-flush">
        <li class="list-group-item" v-for="(notification, idx) in notificationsWithPagination" :key="notification.id"
            :class="{
                'border-bottom': totalPages > pageNumber || idx < notificationsWithPagination.length - 1
            }">
            <NewActivityNotificationComponent :notification="notification" v-if="notification.type === 1" />
            <NewActivityDuplicateStartTimeNotificationComponent :notification="notification"
                v-else-if="notification.type === 2" />
        </li>
        <li class="list-group-item" v-if="totalPages > 1 && totalPages > pageNumber">
            <a class="dropdown-item" @click="setPageNumber">Load more...</a>
        </li>
    </ul>
</template>

<script setup>
import { ref, onMounted, watch } from "vue";

import { notifications } from "@/services/notificationsService";
import { useServerSettingsStore } from "@/stores/serverSettingsStore";

import NewActivityNotificationComponent from "@/components/Notifications/NewActivityNotificationComponent.vue";
import NewActivityDuplicateStartTimeNotificationComponent from "@/components/Notifications/NewActivityDuplicateStartTimeNotificationComponent.vue";

const serverSettingsStore = useServerSettingsStore();
const notificationsWithPagination = ref([]);
const notificationsNotRead = ref(0);
const notificationsNumber = ref(0);
const pageNumber = ref(1);
const numRecords = serverSettingsStore.serverSettings.num_records_per_page || 25;
const totalPages = ref(1);


async function fetchNotifications() {
    try {
        const newNotifications = await notifications.getUserNotificationsWithPagination(pageNumber.value, numRecords);
        notificationsWithPagination.value.push(...newNotifications);
        if (notificationsWithPagination.value.length > 0) {
            for (const notification of notificationsWithPagination.value) {
                if (!notification.read) {
                    notificationsNotRead.value++;
                }
            }
        }
        // Update total pages
        totalPages.value = Math.ceil(notificationsNumber.value / numRecords);
    } catch (error) {
        console.error("Error fetching notifications:", error);
    }
}

async function fetchNotificationsNumber() {
    try {
        notificationsNumber.value = await notifications.getUserNotificationsNumber();
    } catch (error) {
        console.error("Error fetching notifications number:", error);
    }
}

function setPageNumber() {
    // Set the page number to +1.
    pageNumber.value += 1;
}

onMounted(async () => {
    await fetchNotificationsNumber();
    await fetchNotifications();
});

// Watch the page number variable.
watch(pageNumber, fetchNotifications, { immediate: false });
</script>