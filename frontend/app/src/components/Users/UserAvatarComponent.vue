<template>
    <img :src="userPhotoUrl" :alt="altText" :width="width" :height="height" class="rounded-circle" :class="{ 'align-top': alignTopValue == 2 }" v-if="userProp.photo_path">
    <img src="/src/assets/avatar/male1.png" alt="Default Male Avatar" :width="width" :height="height" class="rounded-circle" :class="{ 'align-top': alignTopValue == 2 }" v-else-if="!userProp.photo_path && userProp.gender == 1">
    <img src="/src/assets/avatar/female1.png" alt="Default Female Avatar" :width="width" :height="height" class="rounded-circle" :class="{ 'align-top': alignTopValue == 2 }" v-else>
</template>
  
<script>
import { ref } from 'vue';
  
export default {
    props: {
        userProp: {
            type: Object,
            required: true
        },
        width: {
            type: Number,
            required: true
        },
        height: {
            type: Number,
            required: true
        },
        alignTop: {
            type: Number,
            default: 1,
            required: false
        }
    },
    emits: ['userDeleted'],
    setup(props) {
        const altText = ref('User Avatar');
        const userPhotoUrl = ref(`${import.meta.env.VITE_BACKEND_PROTOCOL}://${import.meta.env.VITE_BACKEND_HOST}/api/v1/${props.userProp.photo_path}`);
        const alignTopValue = ref(props.alignTop);

        return {
            altText,
            userPhotoUrl,
            alignTopValue,
        };
    },
}; 
</script>