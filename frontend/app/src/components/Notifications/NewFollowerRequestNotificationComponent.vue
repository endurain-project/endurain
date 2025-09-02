<template>
  <router-link
    class="dropdown-item link-body-emphasis text-wrap"
    :to="{ name: 'user', params: { id: authStore.user.id }, query: { tab: 'followers' } }"
  >
    <span
      ><b>{{ $t('newFollowerRequestNotificationComponent.newFollowerRequestTitle') }}</b></span
    >
    <br />
    <span class="fw-lighter">
      {{ $t('newFollowerRequestNotificationComponent.newFollowerRequestSubTitle')
      }}{{ notification.options['user_name'] }} - @{{ notification.options['user_username'] }}
    </span>
  </router-link>
</template>

<script setup>
import { computed, watch } from 'vue'
// Importing the i18n
import { useI18n } from 'vue-i18n'
import { useAuthStore } from '@/stores/authStore'

import { notifications } from '@/services/notificationsService'

const authStore = useAuthStore()
const { t } = useI18n()
const emit = defineEmits(['notificationRead'])
const props = defineProps({
  notification: {
    type: Object,
    required: true
  },
  showDropdown: {
    type: Boolean,
    required: true
  }
})

const dropdownState = computed(() => {
  return props.showDropdown
})

function markNotificationAsRead() {
  if (props.notification.read === false && props.showDropdown === true) {
    notifications.markNotificationAsRead(props.notification.id)
    emit('notificationRead', props.notification.id)
  }
}

// Watch the page number variable.
watch(dropdownState, markNotificationAsRead, { immediate: false })
</script>
