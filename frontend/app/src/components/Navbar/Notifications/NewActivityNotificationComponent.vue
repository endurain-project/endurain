<template>
    <router-link class="dropdown-item link-body-emphasis"
        :to="{ name: 'activity', params: { id: notification.options['activity_id'] } }" @click="handleClick">
        <font-awesome-icon :icon="['fas', 'dumbbell']" class="me-1"/>
        <span>
            Teste

            {{ notification.options["activity_id"] }}
        </span>
    </router-link>
</template>

<script setup>
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