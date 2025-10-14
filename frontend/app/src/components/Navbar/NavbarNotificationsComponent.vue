<template>
  <div class="dropdown d-none d-lg-block">
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
          <AdminNewSignUpApprovalRequestNotificationComponent
            :notification="notification"
            :showDropdown="showDropdown"
            v-else-if="notification.type === 101"
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

<script setup lang="ts">
/**
 * Navbar Notifications Component
 *
 * Displays a dropdown menu with user notifications, including real-time updates via WebSocket.
 * Handles pagination, read status, and various notification types.
 */

// ============================================================================
// Section 1: Imports
// ============================================================================
import { ref, onMounted, onUnmounted, watch, type Ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { push } from 'notivue'

import { notifications } from '@/services/notificationsService'
import { useServerSettingsStore } from '@/stores/serverSettingsStore'
import { useAuthStore } from '@/stores/authStore'

import AdminNewSignUpApprovalRequestNotificationComponent from '@/components/Notifications/AdminNewSignUpApprovalRequestNotificationComponent.vue'
import NewAcceptedRequestNotificationComponent from '@/components/Notifications/NewAcceptedRequestNotificationComponent.vue'
import NewActivityNotificationComponent from '@/components/Notifications/NewActivityNotificationComponent.vue'
import NewActivityDuplicateStartTimeNotificationComponent from '@/components/Notifications/NewActivityDuplicateStartTimeNotificationComponent.vue'
import NewFollowerRequestNotificationComponent from '@/components/Notifications/NewFollowerRequestNotificationComponent.vue'
import NoItemsFoundComponents from '@/components/GeneralComponents/NoItemsFoundComponents.vue'
import LoadingComponent from '@/components/GeneralComponents/LoadingComponent.vue'

// ============================================================================
// Section 2: Type Definitions
// ============================================================================

/**
 * Notification object structure matching backend schema
 */
interface Notification {
  id: number
  user_id: number
  type: number
  options: Record<string, unknown>
  read: boolean
  created_at: string
}

/**
 * WebSocket message structure for notification events
 */
interface WebSocketNotificationMessage {
  message: string
  notification_id: number
}

// ============================================================================
// Section 3: Composables & Stores
// ============================================================================
const { t } = useI18n()
const serverSettingsStore = useServerSettingsStore()
const authStore = useAuthStore()

// ============================================================================
// Section 4: Reactive State
// ============================================================================
const isLoading = ref<boolean>(true)
const showDropdown = ref<boolean>(false)
const notificationsWithPagination = ref<Notification[]>([])
const notificationsNotRead = ref<number>(0)
const notificationsNumber = ref<number>(0)
const pageNumber = ref<number>(1)
const numRecords: number = serverSettingsStore.serverSettings.num_records_per_page || 25
const totalPages = ref<number>(1)

// ============================================================================
// Section 5: Main Logic
// ============================================================================

/**
 * Fetch notifications with pagination
 * Updates the notification list and calculates unread count
 */
async function fetchNotifications(): Promise<void> {
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

/**
 * Fetch the total number of notifications for the user
 */
async function fetchNotificationsNumber(): Promise<void> {
  try {
    notificationsNumber.value = await notifications.getUserNotificationsNumber()
  } catch (error) {
    push.error(`${t('navbarNotificationsComponent.errorFetchingNotificationsNumber')} - ${error}`)
  }
}

/**
 * Increment the page number for pagination
 */
function setPageNumber(): void {
  pageNumber.value += 1
}

/**
 * Mark a notification as read in the local state
 * @param notificationId - The ID of the notification to mark as read
 */
function markNotificationAsRead(notificationId: number): void {
  notificationsNotRead.value--
  const notification = notificationsWithPagination.value.find((n) => n.id === notificationId)
  if (notification) {
    notification.read = true
  }
}

/**
 * Fetch a single notification by ID and add it to the list if not already present
 * Used for real-time WebSocket updates
 * @param notificationId - The ID of the notification to fetch
 */
async function fetchNotificationById(notificationId: number): Promise<void> {
  try {
    const newNotification = await notifications.getUserNotificationByID(notificationId)

    if (newNotification) {
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

// ============================================================================
// Section 6: Lifecycle Hooks
// ============================================================================

/**
 * Initialize component and set up WebSocket listener for real-time notifications
 */
onMounted(async () => {
  const websocket = authStore.user_websocket as WebSocket | null
  if (websocket) {
    // Set up websocket message handler
    websocket.onmessage = async (event: MessageEvent) => {
      try {
        const data = JSON.parse(event.data) as WebSocketNotificationMessage
        if (
          data &&
          (data.message === 'NEW_ACTIVITY_NOTIFICATION' ||
            data.message === 'NEW_DUPLICATE_ACTIVITY_START_TIME_NOTIFICATION' ||
            data.message === 'NEW_FOLLOWER_REQUEST_NOTIFICATION' ||
            data.message === 'NEW_FOLLOWER_REQUEST_ACCEPTED_NOTIFICATION' ||
            data.message === 'ADMIN_NEW_SIGN_UP_APPROVAL_REQUEST_NOTIFICATION')
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

/**
 * Clean up WebSocket listener when component unmounts
 */
onUnmounted(() => {
  const websocket = authStore.user_websocket as WebSocket | null
  if (websocket && websocket.onmessage) {
    websocket.onmessage = null
  }
})

/**
 * Watch page number changes and fetch new notifications
 */
watch(pageNumber, fetchNotifications, { immediate: false })
</script>
