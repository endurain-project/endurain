<template>
  <nav class="navbar bg-body-tertiary text-center" v-if="authStore.isAuthenticated">
    <div class="container-fluid justify-content-around">
      <router-link :to="{ name: 'home' }" class="nav-link link-body-emphasis">
        <font-awesome-icon :icon="['fas', 'fa-home']" />
        <br />
        {{ $t('navbarBottomMobileComponent.home') }}
      </router-link>
      <router-link :to="{ name: 'gears' }" class="nav-link link-body-emphasis">
        <font-awesome-icon :icon="['fas', 'fa-bicycle']" />
        <br />
        {{ $t('navbarBottomMobileComponent.gear') }}
      </router-link>
      <router-link :to="{ name: 'health' }" class="nav-link link-body-emphasis">
        <font-awesome-icon :icon="['fas', 'fa-heart']" />
        <br />
        {{ $t('navbarBottomMobileComponent.health') }}
      </router-link>
      <router-link :to="{ name: 'notifications' }" class="nav-link link-body-emphasis">
        <span class="position-relative">
          <font-awesome-icon :icon="['fas', 'fa-bell']" />
          <span
            class="position-absolute top-0 start-100 translate-middle p-1 bg-danger border border-light rounded-circle"
            v-if="notificationsNotRead > 0"
          >
            <span class="visually-hidden">{{ notificationsNotRead }}</span>
          </span>
        </span>
        <br />
        {{ $t('navbarBottomMobileComponent.alerts') }}
      </router-link>
      <router-link :to="{ name: 'menu' }" class="nav-link link-body-emphasis">
        <font-awesome-icon :icon="['fas', 'bars']" />
        <br />
        {{ $t('navbarBottomMobileComponent.menu') }}
      </router-link>
    </div>
  </nav>
  <FooterComponent v-else />
</template>

<script setup>
import { ref, onMounted, onUnmounted, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { push } from 'notivue'

import { notifications } from '@/services/notificationsService'
import { useServerSettingsStore } from '@/stores/serverSettingsStore'
import { useAuthStore } from '@/stores/authStore'

import FooterComponent from '@/components/FooterComponent.vue'

const { t } = useI18n()
const isLoading = ref(true)
const serverSettingsStore = useServerSettingsStore()
const authStore = useAuthStore()
const notificationsWithPagination = ref([])
const notificationsNotRead = ref(0)
const pageNumber = ref(1)
const numRecords = serverSettingsStore.serverSettings.num_records_per_page || 25

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
  } catch (error) {
    push.error(
      `${t('navbarNotificationsComponent.errorFetchingNotificationsPagination')} - ${error}`
    )
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
  if (authStore.isAuthenticated) {
    await fetchNotifications()
  }
  isLoading.value = false
})

onUnmounted(() => {
  if (authStore.user_websocket && authStore.user_websocket.onmessage) {
    authStore.user_websocket.onmessage = null
  }
})
</script>
