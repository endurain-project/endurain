<template>
  <div class="nav-item dropdown d-none d-lg-block">
    <!-- toggle -->
    <a
      class="nav-link link-body-emphasis dropdown-toggle"
      role="button"
      data-bs-toggle="dropdown"
      aria-expanded="false"
      @click="showDropdown = true"
    >
      <span class="position-relative">
        <font-awesome-icon :icon="['fas', 'fa-bell']" />
        <span
          class="position-absolute top-0 start-100 translate-middle p-1 bg-danger border border-light rounded-circle"
          v-if="notificationsNotRead > 0"
        >
          <span class="visually-hidden">{{ notificationsNotRead }}</span>
        </span>
      </span>
    </a>

    <!-- dropdown menu -->
    <ul class="dropdown-menu dropdown-menu-end bg-body-tertiary" style="width: 400px">
      <div v-if="isLoading">
        <LoadingComponent />
      </div>
      <div v-else>
        <li
          v-for="(notification, idx) in notificationsWithPagination"
          :key="notification.id"
          :class="{
            'border-bottom': totalPages > pageNumber || idx < notificationsWithPagination.length - 1
          }"
        >
          <NewActivityNotificationComponent
            :notification="notification"
            :showDropdown="showDropdown"
            v-if="notification.type === 1"
            @notificationRead="markNotificationAsRead"
          />
          <NewActivityDuplicateStartTimeNotificationComponent
            :notification="notification"
            :showDropdown="showDropdown"
            v-else-if="notification.type === 2"
            @notificationRead="markNotificationAsRead"
          />
          <NewFollowerRequestNotificationComponent
            :notification="notification"
            :showDropdown="showDropdown"
            v-else-if="notification.type === 11"
            @notificationRead="markNotificationAsRead"
          />
          <NewAcceptedRequestNotificationComponent
            :notification="notification"
            :showDropdown="showDropdown"
            v-else-if="notification.type === 12"
            @notificationRead="markNotificationAsRead"
          />
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
import { ref, onMounted, onUnmounted, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { push } from 'notivue'

import { notifications } from '@/services/notificationsService'
import { useServerSettingsStore } from '@/stores/serverSettingsStore'
import { useAuthStore } from '@/stores/authStore'

import NewAcceptedRequestNotificationComponent from '@/components/Notifications/NewAcceptedRequestNotificationComponent.vue'
import NewActivityNotificationComponent from '@/components/Notifications/NewActivityNotificationComponent.vue'
import NewActivityDuplicateStartTimeNotificationComponent from '@/components/Notifications/NewActivityDuplicateStartTimeNotificationComponent.vue'
import NewFollowerRequestNotificationComponent from '@/components/Notifications/NewFollowerRequestNotificationComponent.vue'
import NoItemsFoundComponents from '@/components/GeneralComponents/NoItemsFoundComponents.vue'
import LoadingComponent from '@/components/GeneralComponents/LoadingComponent.vue'

const { t } = useI18n()
const isLoading = ref(true)
const showDropdown = ref(false)
const serverSettingsStore = useServerSettingsStore()
const authStore = useAuthStore()
const notificationsWithPagination = ref([])
const notificationsNotRead = ref(0)
const notificationsNumber = ref(0)
const pageNumber = ref(1)
const numRecords = serverSettingsStore.serverSettings.num_records_per_page || 25
const totalPages = ref(1)

async function fetchNotifications() {
  try {
    const newNotifications = await notifications.getUserNotificationsWithPagination(
      pageNumber.value,
      numRecords
    )
    notificationsWithPagination.value.push(...newNotifications)

    notificationsNotRead.value = 0
    if (notificationsWithPagination.value.length > 0) {
      for (const notification of notificationsWithPagination.value) {
        if (!notification.read) {
          notificationsNotRead.value++
        }
      }
    }
    // Update total pages
    totalPages.value = Math.ceil(notificationsNumber.value / numRecords)
  } catch (error) {
    push.error(
      `${t('navbarNotificationsComponent.errorFetchingNotificationsPagination')} - ${error}`
    )
  }
}

async function fetchNotificationsNumber() {
  try {
    notificationsNumber.value = await notifications.getUserNotificationsNumber()
  } catch (error) {
    push.error(`${t('navbarNotificationsComponent.errorFetchingNotificationsNumber')} - ${error}`)
  }
}

function setPageNumber() {
  // Set the page number to +1.
  pageNumber.value += 1
}

function markNotificationAsRead(notificationId) {
  // Decrease the number of notifications not read.
  notificationsNotRead.value--
  // Find the notification and mark it as read.
  const notification = notificationsWithPagination.value.find((n) => n.id === notificationId)
  if (notification) {
    notification.read = true
  }
}

async function fetchNotificationById(notificationId) {
  // Fetch the notification by ID
  try {
    const newNotification = await notifications.getUserNotificationByID(notificationId)

    if (newNotification) {
      // Check if the notification is not already in the list
      const existingNotification = notificationsWithPagination.value.find(
        (n) => n.id === notificationId
      )
      if (!existingNotification) {
        notificationsWithPagination.value.unshift(newNotification)
        if (!newNotification.read) {
          notificationsNotRead.value++
        }
        notificationsNumber.value++
      }
    }
  } catch (error) {
    push.error(`${t('navbarNotificationsComponent.errorFetchingNotificationById')} - ${error}`)
  }
}

onMounted(async () => {
  if (authStore.user_websocket) {
    authStore.user_websocket.on
    // Set up websocket message handler
    authStore.user_websocket.onmessage = async (event) => {
      try {
        const data = JSON.parse(event.data)
        if (
          data &&
          (data.message === 'NEW_ACTIVITY_NOTIFICATION' ||
            data.message === 'NEW_DUPLICATE_ACTIVITY_START_TIME_NOTIFICATION' ||
            data.message === 'NEW_FOLLOWER_REQUEST_NOTIFICATION' ||
            data.message === 'NEW_FOLLOWER_REQUEST_ACCEPTED_NOTIFICATION')
        ) {
          await fetchNotificationById(data.notification_id)
        }
      } catch (error) {
        push.error(
          `${t('navbarNotificationsComponent.errorFetchingMessageFromWebSocket')} - ${error}`
        )
      }
    }
  }
  await fetchNotificationsNumber()
  await fetchNotifications()
  isLoading.value = false
})

// Clean up when component unmounts
onUnmounted(() => {
  if (authStore.user_websocket && authStore.user_websocket.onmessage) {
    authStore.user_websocket.onmessage = null
  }
})

// Watch the page number variable.
watch(pageNumber, fetchNotifications, { immediate: false })
</script>
