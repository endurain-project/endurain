<template>
    <router-link class="dropdown-item link-body-emphasis text-wrap"
        :to="{ name: 'activity', params: { id: notification.options['activity_id'] } }" @click="handleClick">
        <span><b>{{ $t('newActivityNotificationComponent.newActivityTitle') }}</b></span>
        <br>
        <span class="fw-lighter">
            {{ $t('newActivityNotificationComponent.newActivitySubTitle') }}
        </span>
    </router-link>
</template>

<script setup>
// Importing the i18n
import { useI18n } from 'vue-i18n'

const { t } = useI18n()
const props = defineProps({
    notification: {
        type: Object,
        required: true
    }
});

function handleClick(event) {
    // Your custom logic here
}
</script>