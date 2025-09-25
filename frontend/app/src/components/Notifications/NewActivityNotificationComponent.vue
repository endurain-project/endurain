<template>
  <router-link
    class="dropdown-item link-body-emphasis text-wrap"
    :to="{ name: 'activity', params: { id: notification.options['activity_id'] } }"
  >
    <span
      ><b>{{ $t('newActivityNotificationComponent.newActivityTitle') }}</b></span
    >
    <br />
    <span class="fw-lighter">
      {{ $t('newActivityNotificationComponent.newActivitySubTitle') }}
    </span>
  </router-link>
</template>

<script setup>
import { computed, watch } from 'vue'
// Importing the i18n
import { useI18n } from 'vue-i18n'

import { notifications } from '@/services/notificationsService'

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
