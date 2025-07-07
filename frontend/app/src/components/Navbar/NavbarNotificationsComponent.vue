<template>
    <div class="nav-item dropdown d-none d-lg-block">
        <!-- toggle -->
        <a class="nav-link link-body-emphasis dropdown-toggle" role="button" data-bs-toggle="dropdown"
            aria-expanded="false" @click="showDropdown = true">
            <span class="position-relative">
                <font-awesome-icon :icon="['fas', 'fa-bell']" />
                <span
                    class="position-absolute top-0 start-100 translate-middle p-1 bg-danger border border-light rounded-circle"
                    v-if="notificationsNotRead > 0">
                    <span class="visually-hidden">{{ notificationsNotRead }}</span>
                </span>
            </span>
        </a>

        <!-- dropdown menu -->
        <ul class="dropdown-menu dropdown-menu-end bg-body-tertiary" style="width: 400px;">
            <div v-if="isLoading">
                <LoadingComponent />
            </div>
            <div v-else>
                <li v-for="(notification, idx) in notificationsWithPagination" :key="notification.id" :class="{
                    'border-bottom': totalPages > pageNumber || idx < notificationsWithPagination.length - 1
                }">
                    <NewActivityNotificationComponent :notification="notification" :showDropdown="showDropdown"
                        v-if="notification.type === 1" @notificationRead="markNotificationAsRead"/>
                </li>
                <li v-if="totalPages > 1 && totalPages > pageNumber">
                    <a class="dropdown-item" @click="setPageNumber">Load more...</a>
                </li>
                <NoItemsFoundComponents :showShadow="false" v-if="notificationsNumber === 0" />
            </div>
        </ul>
    </div>
</template>

<script setup>
import { ref, onMounted, watch } from "vue";

import { notifications } from "@/services/notificationsService";
import { useServerSettingsStore } from "@/stores/serverSettingsStore";

import NewActivityNotificationComponent from "@/components/Notifications/NewActivityNotificationComponent.vue";
import NoItemsFoundComponents from "@/components/GeneralComponents/NoItemsFoundComponents.vue";
import LoadingComponent from "@/components/GeneralComponents/LoadingComponent.vue";

const isLoading = ref(true);
const showDropdown = ref(false);
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

function markNotificationAsRead(notificationId) {
    // Decrease the number of notifications not read.
    notificationsNotRead.value--;
    // Find the notification and mark it as read.
    const notification = notificationsWithPagination.value.find(n => n.id === notificationId);
    if (notification) {
        notification.read = true;
    }
}

onMounted(async () => {
    await fetchNotificationsNumber();
    await fetchNotifications();
    isLoading.value = false;
});

// Watch the page number variable.
watch(pageNumber, fetchNotifications, { immediate: false });
</script>